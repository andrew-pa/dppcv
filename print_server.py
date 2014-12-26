import os
import sys
import StringIO
import thread
from printcore import *
from pygame import *
from swss import *
import simplejson as json
import xml.etree.ElementTree as xml
import base64
import zipfile
import png
import time

def execwo(v):
        codeOut = StringIO()
        codeErr = StringIO()
        sys.stdout = codeOut
        sys.stderr = codeErr
        exec(v)
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        rv = (codeOut.getvalue(), codeErr.getvalue())
        codeOut.close()
        codeErr.close()
        return rv

class PrintServer(WebSocket):
        def init(self, udata):
		self.graphics = udata['graphics']
		self.config = udata['config']
                self.upload_path = os.path.expanduser("~/.dppcv/")
		self.allow_exec_py = self.config.has_key('allow-exec-python')

        def print_file(self,filename):
                if zipfile.is_zipfile(self.upload_path+filename):
                        #load zip file
                        zf = zipfile.ZipFile(self.upload_path+filename);
                        #lpf = zf.open(fname+str(i).rjust(4, '0')+'.png')
                        #start gcode run
                        self.graphics.start_print((zf,filename.split('.')[0]))
                else:
                        print "File: " + filename + " is not a zip file"

        def send_ack(self, code, extra={}):
                jm = extra
                jm["ack"]=code
                jm["connected"] = not self.graphics.printer is None
                if not self.graphics.printer is None:
                        jm["printing"] = self.graphics.printing
                        if self.graphics.printer.printing:
                               jm["print-status"] = self.graphics.current_layer
                        jm["paused"] = self.graphics.paused
                self.sendMessage(json.dumps(jm))
        def handleMessage(self):
                if self.data is None:
                        pass
                msg = json.loads(str(self.data))
                #if msg["cmd"] != 'upload-file':
		print(msg)
                if msg["cmd"] == "nop":
                    self.send_ack(3)
		    return
                elif msg["cmd"] == "connect":
                    self.graphics.initprintcore("/dev/"+msg["port"], int(msg["baudrate"]))
                    self.send_ack(0)
		    return
                elif msg["cmd"] == "disconnect":
                    if not (self.graphics.printer is None):
                        self.graphics.printer.disconnect()
                        self.graphics.printer = None
                        self.send_ack(0)
			return
                    else:
                        self.send_ack(1)
			return
                #!!Nasty security hole, but useful for remote debugging!!
                elif self.allow_exec_py and msg["cmd"] == "exec-python":
				outv = execwo(msg["code"])
                                rmg = { "out": outv[0], "err": outv[1] }
                                self.send_ack(0, rmg)
				return
                elif msg["cmd"] == "upload-file":
                                if int(msg["chunk"]) == 0:
                                        self.ulfile = open(self.upload_path+msg["filename"], "ab+")
                                self.ulfile.write(base64.b64decode(msg["data"]))
                                if msg.has_key("last-chunk"):
                                        self.ulfile.flush()
                                        self.ulfile.close()
                                self.send_ack(8)
				return
                if not self.graphics.printer is None:
                                if msg["cmd"] == "pause-resume":
                                        if self.is_paused:
                                                self.graphics.resume()
                                                self.is_paused = False
                                        else:
                                                self.graphics.pause()
                                                self.is_paused = True
                                        self.send_ack(0)
					return
                                elif msg["cmd"] == "print-file":
                                        self.print_file(msg["filename"])
                                        self.send_ack(0)
					return
                                elif msg["cmd"] == "send-immediate":
                                        self.graphics.printer.send(msg["gcode"])
                                        #print self.graphics.printer.log
					self.send_ack(0)
                return


        def handleConnected(self):
                self.connected = False
                print self.address, 'connected'

        def handleClose(self):
                print self.address, 'closed'
