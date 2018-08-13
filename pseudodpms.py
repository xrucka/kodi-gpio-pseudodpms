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
from threading import Timer

SYSFSPATH = "/sys/class/gpio"

class GPIOPin:
    def __init__(self, pin, direction):
        self.pin = pin
        self.direction = direction
    
    def pinpath(self):
        return "%s/gpio%d" % (SYSFSPATH, self.pin)
    
    def __enter__(self):
        try:
            exportfd = open("%s/export" % (SYSFSPATH), 'w')
            exportfd.write(str(self.pin))
        except IOError as err:
            pass
        finally:
            if exportfd:
                exportfd.close()
       
        directionfd = open("%s/direction" % (self.pinpath()), 'w')
        directionfd.write(self.direction)
        directionfd.close()
        
        return self
    
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
    
    def __exit__(self, type, value, traceback):
        exportfd = open("%s/unexport" % (SYSFSPATH), 'w')
        exportfd.write(str(self.pin))
        exportfd.close()



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
        
        self.load_settings()
    
    def load_settings(self):
        self.inactivity_timeout = float(self.addon.getSetting("inactivity_timeout")) * 60
        self.use_sense = self.addon.getSetting('use_sense') == "true"
        self.sense_pin = int(self.addon.getSetting("sense_pin"))
        self.toggle_pin = int(self.addon.getSetting("toggle_pin"))
        self.toggle_duration = float(self.addon.getSetting("toggle_duration"))
    
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
            if self.sense_off():
                xbmc.log("Sense claims display allready shut down", level=xbmc.LOGERROR)
                return
        
        self.toggle()
    
    def start_display(self):
        if self.use_sense:
            if self.sense_on():
                xbmc.log("Sense claims display allready on", level=xbmc.LOGERROR)
                return
        
        self.toggle()
    
    def sense_on(self):
        return self.sense(True)
    
    def sense_off(self):
        return self.sense(False)
    
    def sense(self, expected):
        with GPIOPin(self.sense_pin, "in") as _pin:
            val = _pin.readValue()
            return _pin.readValue() == expected
    
    def toggle(self):
        pin = self.toggle_pin
        duration = self.toggle_duration
        
        with GPIOPin(pin, "out") as _pin:
            _pin.writeValue(True)
            time.sleep(duration)
            _pin.writeValue(False)

if __name__ == '__main__':
    pseudo = PseudoDPMSAddon()
    
    while not pseudo.monitor.abortRequested():
        if pseudo.monitor.waitForAbort():
            pass
