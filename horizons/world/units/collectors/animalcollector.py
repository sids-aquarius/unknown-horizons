# ###################################################
# Copyright (C) 2011 The Unknown Horizons Team
# team@unknown-horizons.org
# This file is part of Unknown Horizons.
#
# Unknown Horizons is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# ###################################################

import horizons.main
from horizons.scheduler import Scheduler

from horizons.world.storageholder import StorageHolder
from horizons.util import Point, Circle
from horizons.world.units.movingobject import MoveNotPossible
from horizons.constants import GAME_SPEED
from horizons.world.units.collectors.buildingcollector import BuildingCollector


class AnimalCollector(BuildingCollector):
	""" Collector that gets resources from animals.
	Behaviour (timeline):
	 - search for an animal which has resources to pick up
	 - tell animal to stop when its current job is done
	 - wait for callback from this animal, notifying that we can pick it up
	 - walk to animal
	 - walk home (with animal walking along)
	 - stay at home building for a while
	 - release animal
	 """
	kill_animal = False # whether we kill the animals

	def __init__(self, *args, **kwargs):
		super(AnimalCollector, self).__init__(*args, **kwargs)

	def load(self, db, worldid):
		super(AnimalCollector, self).load(db, worldid)

	def apply_state(self, state, remaining_ticks = None):
		super(AnimalCollector, self).apply_state(state, remaining_ticks)
		if state == self.states.waiting_for_animal_to_stop:
			# register at target
			self.setup_new_job()
			self.stop_animal()
		elif state == self.states.moving_home:
			if not self.kill_animal:
				self.setup_new_job() # register at target if it's still alive

	def cancel(self, continue_action = None):
		if self.job is not None:
			if self.state == self.states.waiting_for_animal_to_stop:
				self.job.object.remove_stop_after_job()
		super(AnimalCollector, self).cancel(continue_action=continue_action)

	def begin_current_job(self):
		"""Tell the animal to stop."""
		self.setup_new_job()
		self.stop_animal()
		self.state = self.states.waiting_for_animal_to_stop

	def pickup_animal(self):
		"""Moves collector to animal. Called by animal when it actually stopped"""
		self.show()
		try:
			self.move(self.job.object.position, self.begin_working)
		except MoveNotPossible:
			# the animal is now unreachable.
			self.job.object.search_job()
			self.state = self.states.idle
			self.cancel(continue_action=self.search_job)
			return
		self.state = self.states.moving_to_target

	def finish_working(self):
		"""Called when collector arrives at the animal. Move home with the animal"""
		if self.kill_animal:
			# get res now, and kill animal right after
			super(AnimalCollector, self).finish_working()
		else:
			self.move_home(callback=self.reached_home)
		self.get_animal() # get or kill animal

	def reached_home(self):
		"""Transfer res to home building and such. Called when collector arrives at it's home"""
		if not self.kill_animal:
			# sheep and herder are inside the building now, pretending to work.
			super(AnimalCollector, self).finish_working(collector_already_home=True)
			self.release_animal()
		super(AnimalCollector, self).reached_home()

	def get_buildings_in_range(self, reslist=None):
		return self.get_animals_in_range(reslist)

	def get_animals_in_range(self, reslist=None):
		return self.home_building.animals

	def stop_animal(self):
		"""Tell animal to stop at the next occasion"""
		self.job.object.stop_after_job(self)

	def get_animal(self):
		"""Sends animal to collectors home building"""
		self.log.debug("%s getting animal %s",self, self.job.object)
		if self.kill_animal:
			self.job.object.die()
		else:
			self.job.object.move(self.home_building.position, destination_in_building = True, \
			                     action='move_full')

	def release_animal(self):
		"""Let animal free after shearing and schedules search for a new job for animal."""
		if not self.kill_animal:
			self.log.debug("%s releasing animal %s",self, self.job.object)
			Scheduler().add_new_object(self.job.object.search_job, self.job.object, \
			                           GAME_SPEED.TICKS_PER_SECOND)


class FarmAnimalCollector(AnimalCollector):
	def get_animals_in_range(self, reslist=None):
		"""Returns animals from buildings in range"""
		circle = Circle(self.home_building.position.center(), self.home_building.radius)
		# don't consider res when searching for buildings, since only their animals are
		# the acctual providers
		buildings = self.home_building.island.get_providers_in_range(circle)
		animal_lists = ( building.animals for building in buildings if hasattr(building, 'animals'))
		# use overloaded + for lists here in sum
		return sum(animal_lists, [])


class HunterCollector(AnimalCollector):
	kill_animal = True

	def get_animals_in_range(self, res=None):
		return self.home_building.island.wild_animals
