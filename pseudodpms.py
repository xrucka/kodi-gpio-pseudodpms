#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#     Copyright (C) 2018 Lukas Rucka
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import xbmcaddon
import xbmc
import time
import os.path
from threading import Timer

SYSFSPATH = "/sys/class/gpio"

class GPIOPin:
    def __init__(self, pin):
        self.pin = pin
        self.wanted = "in"

    def check_configuration(self, query):
        directionfd = open("%s/direction" % (self.pinpath()), 'r')
        old_direction = directionfd.read().strip()
        directionfd.close()
        return query == old_direction

    def reconfigure(self, new_direction, override = False):
        directionfd = open("%s/direction" % (self.pinpath()), 'r')
        old_direction = directionfd.read().strip()
        directionfd.close()
 
        if old_direction == new_direction:
            return True

        write_direction = None

        if new_direction == "out":
            write_direction = new_direction
        elif old_direction == "old" and new_direction == "in":
            pass

        if override:
            write_direction = new_direction
    
        if write_direction is None:
            return False

        self.wanted = write_direction
        if self.wanted != old_direction:
            directionfd = open("%s/direction" % (self.pinpath()), 'w')
            directionfd.write(write_direction)
            directionfd.close()

        return True
    
    def pinpath(self):
        return "%s/gpio%d" % (SYSFSPATH, self.pin)

    def export(self):
        try:
            exportfd = open("%s/export" % (SYSFSPATH), 'w')
            exportfd.write(str(self.pin))
        except IOError as err:
            return False
        finally:
            if exportfd:
                exportfd.close()

            return True

    def unexport(self):
        try:
            exportfd = open("%s/unexport" % (SYSFSPATH), 'w')
            exportfd.write(str(self.pin))
        except IOError as err:
            return False
        finally:
            if exportfd:
                exportfd.close()

            return True

    def isExported(self):
        return os.path.isdir(self.pinpath())
 
    def checkOrReexport(self):
        if not self.isExported():
            if not self.export():
                return False

        if self.wanted is not None:
            self.reconfigure(self.wanted, True)

        return True

    def readValue(self):
        fd = open("%s/value" % (self.pinpath()), 'r')
        value = fd.read().strip()
        fd.close()
        
        xbmc.log("GPIO Pin %d: %s" % (self.pin, value), level=xbmc.LOGDEBUG)
        return bool(value != '0' and value != '')
    
    def writeValue(self, value):
        fd = open("%s/value" % (self.pinpath()), 'w')
        pinval = 1 if value else 0
        fd.write(str(pinval))
        fd.close()
    

class PseudoDPMSAddon():

    class ScreensaverMonitor(xbmc.Monitor):
        def __init__(self, parent):
            xbmc.Monitor.__init__(self)
            self.parent = parent
        
        def onScreensaverActivated(self):
            self.parent.onScreensaverActivated()
        
        def onScreensaverDeactivated(self):
            self.parent.onScreensaverDeactivated()
        
        def onSettingsChanged(self):
            self.parent.load_settings();
    
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.addon_name = self.addon.getAddonInfo('name')
        self.addon_path = self.addon.getAddonInfo('path')
        self.monitor = self.ScreensaverMonitor(self)
        
        self.inactivity_timer = None
        
        self.inactivity_timeout = None
        self.toggle_pin = None;
        self.sense_pin = None
        self.use_sense = None
        self.toggle_duration = None
        self.toggle_mode_pulse = None
        
        self.sense_handler = None
        self.toggle_handler = None
        
        self.load_settings()
    
    def load_settings(self):
        old_sense = self.sense_pin
        old_toggle = self.toggle_pin
        
        self.inactivity_timeout = float(self.addon.getSetting("inactivity_timeout")) * 60
        self.use_sense = self.addon.getSetting('use_sense') == "true"
        self.sense_pin = int(self.addon.getSetting("sense_pin"))
        self.toggle_pin = int(self.addon.getSetting("toggle_pin"))
        self.toggle_duration = float(self.addon.getSetting("toggle_duration"))
        self.toggle_mode_pulse = int(self.addon.getSetting("toggle_mode")) == 0
        
        self.reconfigure(old_sense, old_toggle)

    def unconfigure(self, old_sense, old_toggle): 
        if old_sense != self.sense_pin and self.sense_handler is not None:
            self.sense_handler.unexport()

        if old_toggle != self.toggle_pin and self.sense_handler is not None:
            self.toggle_handler.unexport()

    def reconfigure(self, old_sense, old_toggle):
        self.unconfigure(old_sense, old_toggle)

        self.sense_handler = GPIOPin(self.sense_pin)
        self.sense_handler.checkOrReexport()
        self.sense_handler.reconfigure("in")
        
        if self.sense_pin == self.toggle_pin or not self.use_sense:
            self.toggle_handler = self.sense_handler
        else:
            self.toggle_handler = GPIOPin(self.toggle_pin)
        self.toggle_handler.checkOrReexport()
        self.toggle_handler.reconfigure("out")
        
    def onScreensaverActivated(self):
        if self.inactivity_timer:
            self.inactivity_timer.cancel()
        
        self.inactivity_timer = Timer(self.inactivity_timeout, self.shutdown_display)
        self.inactivity_timer.start()
    
    def onScreensaverDeactivated(self):
        if self.inactivity_timer:
            self.inactivity_timer.cancel()
            self.inactivity_timer = None
        
        self.start_display()
    
    def shutdown_display(self):
        self.inactivity_timer = None
        
        if self.use_sense:
            self.sense_handler.checkOrReexport()
            if self.sense_off():
                xbmc.log("Sense claims display allready shut down", level=xbmc.LOGERROR)
                return
        
        self.toggle_handler.checkOrReexport()
        self.toggle(False)
    
    def start_display(self):
        if self.use_sense:
            self.sense_handler.checkOrReexport()
            if self.sense_on():
                xbmc.log("Sense claims display allready on", level=xbmc.LOGERROR)
                return
        
        self.toggle_handler.checkOrReexport()
        self.toggle(True)
    
    def sense_on(self):
        return self.sense(True)
    
    def sense_off(self):
        return self.sense(False)
    
    def sense(self, expected):
        return self.sense_handler.readValue() == expected
    
    def toggle_pulse(self, goal):
        duration = self.toggle_duration
        
        self.toggle_handler.writeValue(True)
        time.sleep(duration)
        self.toggle_handler.writeValue(False)

    def toggle_hold(self, goal):
        self.toggle_handler.writeValue(goal)

    def toggle(self, goal):
        if self.toggle_mode_pulse:
            self.toggle_pulse(goal)
        else:
            self.toggle_hold(goal)

if __name__ == '__main__':
    pseudo = PseudoDPMSAddon()
    
    while not pseudo.monitor.abortRequested():
        if pseudo.monitor.waitForAbort():
            pass
    pseudo.unconfigure(None, None)


