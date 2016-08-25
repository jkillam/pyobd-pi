#!/usr/bin/env python

import obd_io
import serial
import platform
import obd_sensors
from datetime import datetime
import time
import getpass
import os
import json

from obd_utils import scanSerial
from debugEvent import debug_display

class OBD_Recorder():
    def __init__(self, path, log_items):
        #self.status_file = open(os.path.dirname(os.path.realpath(__file__)) + "/status.json", "w")
        self.status_file_path = os.path.dirname(os.path.realpath(__file__)) + "/status.json"
        self.port = None
        self.sensorlist = []
        localtime = time.localtime(time.time())
        filename = path+"car-"+str(localtime[0])+"-"+str(localtime[1])+"-"+str(localtime[2])+"-"+str(localtime[3])+"-"+str(localtime[4])+"-"+str(localtime[5])+".log"
        self.log_file = open(filename, "w", 128)
        #self.log_file.write("Time,RPM,MPH,Throttle,Load,Fuel Status\n");

        for item in log_items:
            self.add_log_item(item)
            self.log_file.write(item + ",")
        self.log_file.write("\n")
        self.gear_ratios = [34/13, 39/21, 36/23, 27/20, 26/21, 25/22]
        #log_formatter = logging.Formatter('%(asctime)s.%(msecs).03d,%(message)s', "%H:%M:%S")

    def connect(self):
        portnames = scanSerial()
        #portnames = ['COM10']
        print portnames
        for port in portnames:
            self.port = obd_io.OBDPort(port, None, 2, 2)
            if(self.port.State == 0):
                self.port.close()
                self.port = None
            else:
                break

        if(self.port):
            print "Connected to "+self.port.port.name
            
    def is_connected(self):
        return self.port
        
    def add_log_item(self, item):
        for index, e in enumerate(obd_sensors.SENSORS):
            if(item == e.shortname):
                self.sensorlist.append(index)
                print "Logging item: "+e.name
                break
            
            
    def record_data(self):
        with open(self.status_file_path) as stat_file:
            #print "file contents " + self.status_file_path
            #print stat_file.readlines()
            saved_data = json.load(stat_file)
        #necessary_sensors = ["fuel_level", "speed", "maf", "rpm", "fuel_air_equiv"] # Sensor values needed to calculate other values, right now this list does nothing
        if(self.port is None):
            return None
        
        print "Logging started"
        
        while 1:
            localtime = datetime.now()
            current_time = str(localtime.hour)+":"+str(localtime.minute)+":"+str(localtime.second)+"."+str(localtime.microsecond)
            log_string = current_time
            results = {}
            for index in self.sensorlist:
                (name, value, unit) = self.port.sensor(index)
                if value == "NODATA":
                    (name, value, unit) = self.port.sensor(index)
                log_string = log_string + ","+str(value)
                results[obd_sensors.SENSORS[index].shortname] = value;
                #print log_string
            gear = self.calculate_gear(results.get("rpm", "NODATA"), results.get("speed", "NODATA"))
            inst_fuel_economy = self.calculate_inst_fuel_economy(results.get("speed", "NODATA"), results.get("maf", "NODATA"), results.get("fuel_air_equiv", "NODATA"))
            log_string = log_string + "," + str(gear) + ", " + str(inst_fuel_economy) + ", " + str(saved_data["dist_since_fill"])
            self.log_file.write(log_string+"\n")
            
            ## Store certain parameters to be read upon reboot, and values to determine overall fuel economy
            try:
                if results.get("fuel_level") > saved_data["fuel_level"] * 1.5 or not isinstance(saved_data["dist_since_fill"], (int, float, long)):
                    # Gas tank has been filled, *1.5 is just a buffer; or previously determined value of dist_since_last_fill was not a number
                    saved_data["dist_since_fill"] = results.get("dist_since_clear") # this could be none, need to account for that
                saved_data["fuel_level"] = results.get("fuel_level")
                if results.get("dist_since_clear") < saved_data["dist_since_fill"]: # DTC must have been reset, adjust dist_at_last_fill
                    if saved_data["dist_at_last_fill"] > 0:
                        saved_data["dist_at_last_fill"] = saved_data["dist_since_fill"] * -1
                    else:
                        saved_data["dist_at_last_fill"] = saved_data["dist_at_last_fill"] - saved_data["dist_since_fill"]
                saved_data["dist_since_fill"] = results.get("dist_since_clear") - saved_data["dist_at_last_fill"]
                # Save json data to status file
                with open(self.status_file_path, 'w') as stat_file:
                    json.dump(saved_data, stat_file)
            except:
                print "coundn't save data"
            

            
    def calculate_gear(self, rpm, speed):
        if speed == "" or speed == 0:
            return 0
        if rpm == "" or rpm == 0:
            return 0
        if isinstance(speed, basestring) or isinstance(rpm, basestring):
            return "NODATA"
        rps = rpm/60
        mps = (speed*1000.0)/3600
        
        primary_gear = 85/46 #street triple
        final_drive  = 47/16
        
        tyre_circumference = 1.978 #meters

        current_gear_ratio = (rps*tyre_circumference)/(mps*primary_gear*final_drive)
        
        #print current_gear_ratio
        gear = min((abs(current_gear_ratio - i), i) for i in self.gear_ratios)[1] 
        return gear

    def calculate_inst_fuel_economy(self, speed, maf, fa_equiv):
        if isinstance(speed, basestring) or isinstance(maf, basestring) or isinstance(fa_equiv, basestring):
            return "NODATA"
        if speed < 5:
            speed = 5
        fuel_per_second = maf*14.6*fa_equiv * .755 / 1000 # L/s
        dist_per_second = speed / 3600.0 #km/s
        
        return fuel_per_second / dist_per_second * 100
        
        
username = getpass.getuser()  
logitems = ["rpm", "speed", "throttle_pos", #"load",
            "fuel_status", "maf", "fuel_air_equiv",
            #"fuel_level", "dist_since_clear"
            ]
o = OBD_Recorder(os.path.dirname(os.path.realpath(__file__))+'/log/', logitems)
o.connect()

count = 0
while not o.is_connected():
    print "Not connected, trying again"
    o.connect()
    count = count + 1
    if count == 5:
        break
if o.is_connected():
    o.record_data()
else:
    print "Not connected, giving up"
