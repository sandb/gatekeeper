#!/usr/bin/python

import serial   #serial communication
import re       #regular expressions
import logging  #hmm what could this be for?
import os       #to call external stuff
import signal  #catch kill signall
import time     #for the sleep function
import select  #for select.error
from errno import EINTR #read interrupt
import traceback #for stacktrace

#setup logging
LOG_FILENAME = '/opt/gatekeeper/gatekeeper.log'
FORMAT = "%(asctime)-12s: %(levelname)-8s - %(message)s"
logging.basicConfig(filename=LOG_FILENAME,level=logging.INFO,format=FORMAT)
log = logging.getLogger("GateKeeper")

#setup whitelist file
whitelist_file = "/opt/gatekeeper/whitelist"

#setup serial ports of gatecontroller and huawei
gatecontroller_port = "/dev/serial/by-id/usb-Texas_Instruments_Texas_Instruments_MSP-FET430UIF_07FF41CE96165627-if00"
huawei_port = "/dev/serial/by-id/usb-HUAWEI_Technologies_HUAWEI_Mobile-if01-port0"

class GateController:

  def __init__(self, serialPort):
    self.serial = serial.Serial(serialPort, 2400)
    log.debug("Launchpad initialized on serial port " + serialPort)

  def openGate(self):
    self.serial.write('u')
    log.debug("Asking the LaunchPad GateKeeper to open the gate")
    
  def closeGate(self):
    self.serial.write('d')
    log.debug("Asking the LaunchPad GateKeeper to stop opening the gate")

  def closeSerial(self):
    self.serial.close()
    log.debug("LaunchPad GateKeeper connection closed")

class GateKeeper:

  def __init__(self):
    self.public = False
    self.read_whitelist()
    self.enable_caller_id()
    self.data_channel = serial.Serial(huawei_port, 115200)
    self.gateController = GateController(gatecontroller_port)

  def read_whitelist(self):
    self.public = False
    self.whitelist = {}
    file = open(whitelist_file,'r')
    entry_pattern = re.compile('([0-9][0-9]+?) (.*)')
    line = file.readline()
    while line:
      entry_match = entry_pattern.match(line)
      if entry_match:
        number = entry_match.group(1)
        name = entry_match.group(2)
        self.whitelist[number] = name
      elif line.strip() == '*':
        self.public = True     
      line = file.readline()
    if self.public:
      log.info("Gatekeeper is in PUBLIC mode")
    else:
      log.info("Gatekeeper is in PRIVATE mode")
    file.close()
    log.debug("Whitelist " + str(self.whitelist))

  def enable_caller_id(self):
    command_channel = serial.Serial(huawei_port, 115200)
    command_channel.open()
    command_channel.write("AT+CLIP=1" + "\r\n")
    command_channel.close()
    log.debug("Enabled caller ID")

  def start(self):
    try: 
      self.wait_for_call()
    except select.error, v:
      if v[0] == EINTR:
        log.debug("Interrupt while waiting for call, cleanup should be done.")
      else:
        log.warning("Unexpected select exception, shutting down!")
        raise
    else:
      log.warning("Unexpected exception, shutting down!")

  def whitelist_modification(self):
    stats = os.stat(whitelist_file)
    return time.localtime(stats[8])
  
  def wait_for_call(self):
    self.data_channel.open()
    call_id_pattern = re.compile('.*CLIP.*"\+([0-9]+)",.*')
    last_modification = self.whitelist_modification()
    while True:
      char = ''
      buffer = ""
      #A blocking call reading data from the serial connection
      #A single byte at a time, as advised from Bert.
      while char != '\n':
        char = self.data_channel.read(1)
        buffer = buffer + char

      call_id_match = call_id_pattern.match(buffer)
      log.debug("Data from data channel: " + buffer.strip())
      #read text file again if it is modified
      if last_modification < self.whitelist_modification():
        self.read_whitelist()
        last_modification = self.whitelist_modification()
        log.info("Reread whitelist.")
      if call_id_match:
        number = call_id_match.group(1)
        self.handle_call(number)
  
  def handle_call(self,number):
    if number in self.whitelist or self.public:
      self.gateController.openGate()
      if number in self.whitelist:
        log.info("Opened the gate for " + self.whitelist[number] + " (" + number + ").")
      else:
        log.info("Opened the gate for an anonymous hacker with number: (" + number + ").")
    else:
      log.info("Did not open the gate for "  + number + ", number  is not kown.")
      
  def stop_gatekeeping(self):
    self.data_channel.close()
    self.gateController.closeSerial()
    log.debug("Cleanup finished.") 

gatekeeper = None

def shutdown_handler(signum, frame):
  gatekeeper.stop_gatekeeping()
  log.info("Stopping GateKeeper.") 

def main():
  try:
    global gatekeeper
    gatekeeper = GateKeeper()
    
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM,shutdown_handler)
    
    gatekeeper.start()
  except Exception, e:
    log.info("GateKeeper was terminated due to an exception: %s (%s)" % (e, type(e)))
    raise

log.info("Started GateKeeper.")
main()
