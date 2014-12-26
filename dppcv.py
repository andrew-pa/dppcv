#!/usr/bin/python2

import os
import sys
import StringIO
import thread
from printcore import *
from pyopengles.pyopengles import *
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

printer_init = False
printer = None
config = { 'not-yet-loaded':True }

class Graphics():
        def showlog(self,shader):
                """Prints the compile log for a shader"""
                N=1024
                log=(ctypes.c_char*N)()
                loglen=ctypes.c_int()
                opengles.glGetShaderInfoLog(shader,N,ctypes.byref(loglen),ctypes.byref(log))
                print log.value

        def showprogramlog(self,shader):
                """Prints the compile log for a program"""
                N=1024
                log=(ctypes.c_char*N)()
                loglen=ctypes.c_int()
                opengles.glGetProgramInfoLog(shader,N,ctypes.byref(loglen),ctypes.byref(log))
                print log.value
        
        def __init__(self, conf):
                self.egl = EGL()
		self.cf = conf
		self.profile = xml.parse(os.path.expanduser('~/.dppcv/')+self.cf['profile-path'])
                self.vertex_data = eglfloats((-1.0,-1.0,1.0,1.0,
                         1.0,-1.0,1.0,1.0,
                         1.0,1.0,1.0,1.0,
                         -1.0,1.0,1.0,1.0))
                self.vshader_source = ctypes.c_char_p(
                      "attribute vec4 vertex;"
                      "varying vec2 tcoord;"
                      "void main(void) {"
                      "  gl_Position = vertex;"
                      "  tcoord = vertex.xy*vec2(0.5,-0.5)+0.5;"
                      "}")
              
                self.fshader_source = ctypes.c_char_p(
                      "uniform sampler2D texture;"
                      "uniform bool show_texture;"
                      "varying vec2 tcoord;"
                      "void main(void) {"
                      "   gl_FragColor = show_texture ? texture2D(texture,tcoord) : vec4(0.0,0.0,0.0,1.0);"
                      "}")
                vshader = opengles.glCreateShader(GL_VERTEX_SHADER)
                opengles.glShaderSource(vshader, 1, ctypes.byref(self.vshader_source), 0)
                opengles.glCompileShader(vshader)
                self.showlog(vshader)
                
                fshader = opengles.glCreateShader(GL_FRAGMENT_SHADER)
                opengles.glShaderSource(fshader, 1, ctypes.byref(self.fshader_source), 0)
                opengles.glCompileShader(fshader)
                self.showlog(fshader)
                
                self.check()
                program = opengles.glCreateProgram()
                opengles.glAttachShader(program, vshader)
                opengles.glAttachShader(program, fshader)
                opengles.glLinkProgram(program)
                self.program = program
                self.showprogramlog(program)
                self.check()
                self.attr_vertex = opengles.glGetAttribLocation(program, "vertex")
                self.check()
                self.unif_tex = opengles.glGetUniformLocation(program, "texture")
                self.unif_showtex = opengles.glGetUniformLocation(program, "show_texture")
                self.check()
                self.buf = eglint()
                opengles.glGenBuffers(1,ctypes.byref(self.buf))
                opengles.glBindBuffer(GL_ARRAY_BUFFER, self.buf)
                opengles.glBufferData(GL_ARRAY_BUFFER, ctypes.sizeof(self.vertex_data),
                                      ctypes.byref(self.vertex_data), GL_STATIC_DRAW)
                self.check()
                opengles.glVertexAttribPointer(self.attr_vertex, 4, GL_FLOAT, 0, 16, 0);
                opengles.glEnableVertexAttribArray(self.attr_vertex)
                self.check()
                self.layers = []
                self.tex = eglint()
                opengles.glGenTextures(1,ctypes.byref(self.tex))
                opengles.glBindTexture(GL_TEXTURE_2D,self.tex)
                opengles.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 1, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE,
                                      ctypes.c_char_p('\x00\x00\x00\xff'))
                
                opengles.glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, eglfloat(GL_NEAREST))
                opengles.glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, eglfloat(GL_NEAREST))
                self.check()
                self.printing = False
                self.paused = False
                self.current_layer = -1
                self.layer_timer = 0
                self.printer = None
	def initprintcore(self, port, baudrate):
		self.printer = printcore(port, baudrate)
        def pause(self):
                self.paused = True
        def resume(self):
                self.paused = False
                
        def clear_layers(self):
                self.layers = []
        def add_layer(self, f):
                pr = png.Reader(file=f)
                dpr = pr.asRGBA8()
		ds = ctypes.c_buffer(dpr[0]*dpr[1]*4)
		i = 0
                for r in dpr[2]:
			for v in r:
				ds[i] = chr(v)
				i = i + 1
                self.layers.append((dpr[0],dpr[1],ds))
        def show_layer(self, i):
                dpr = self.layers[i]
                opengles.glBindTexture(GL_TEXTURE_2D, self.tex)
                opengles.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, dpr[0], dpr[1], 0, GL_RGBA, GL_UNSIGNED_BYTE,
                                      ctypes.c_char_p(dpr[2].raw))
        def check(self):
                e=opengles.glGetError()
                if e:
                    print hex(e)
                    raise ValueError
	def process_gcode(self, gcode):
		lines = gcode.split('\n')
		for ln in lines:
			cmd = ln.partition(';')[0] #remove comments
			if not cmd.isspace():
				cmd = cmd.replace('$ZLiftDist', self.profile.find('LiftDistance').text)
				cmd = cmd.replace('$ZLiftRate', self.profile.find('LiftFeedRate').text)
				cmd = cmd.replace('$LayerThickness', self.profile.find('InkConfig').find('SliceHeight').text)
				cmd = cmd.replace('$ZDir', '1')
				print 'sending command: ' + cmd
				self.printer.send(cmd)
        def start_print(self):
                self.current_layer = 0
                self.printing = True
                self.paused = False
                self.layer_timer = float(self.profile.find('InkConfig').find('LayerTime').text)
                self.process_gcode(self.profile.find('GCodeHeader').text)
                self.show_layer(0)
        def update(self, dt):
                if self.printing and not self.paused:
                        self.layer_timer -= dt
                        if self.layer_timer <= 0:
                                opengles.glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT) #make sure the display is clear while we move the bed
                                opengles.eglSwapBuffers(self.egl.display, self.egl.surface)                
                                self.current_layer = self.current_layer + 1
				print "Next Layer: " + str(self.current_layer)
                                if self.current_layer > len(self.layers):
                                        self.process_gcode(self.profile.find('GCodeFooter').text)
					self.current_layer = -1
                                        self.printing = False
                                        return
                                self.show_layer(self.current_layer)
                                self.layer_timer=float(self.profile.find('InkConfig').find('LayerTime').text)
                                self.process_gcode(self.profile.find('GCodeLift').text)
                                #while not self.printer.clear:
                                        #pass
                opengles.glClearColor(eglfloat(0.0), eglfloat(0.0), eglfloat(0.0), eglfloat(1.0))
                opengles.glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
                opengles.glBindBuffer(GL_ARRAY_BUFFER, self.buf)
                opengles.glUseProgram(self.program)
                opengles.glUniform1i(self.unif_tex, 0)
                opengles.glUniform1i(self.unif_showtex, 1)#int(self.printing and not self.paused))
                opengles.glDrawArrays(GL_TRIANGLE_FAN, 0, 4)
                opengles.glFinish()
                opengles.eglSwapBuffers(self.egl.display, self.egl.surface)
        

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
                        #extract PNGs + load to GL textures (cashed?)
                        self.graphics.clear_layers()
                        i = 0
                        fname = filename.split('.')[0];
                        lpf = zf.open(fname+str(i).rjust(4, '0')+'.png')
                        
                        while True:
                               self.graphics.add_layer(lpf)
                               i = i + 1
                               try:
				       print "Loading file: " + fname+str(i).rjust(4, '0') + '.png'
                                       lpf = zf.open(fname+str(i).rjust(4, '0')+'.png')
                               except:
                                       break         
                        #start gcode run
                        self.graphics.start_print()
                else:
                        pass
                
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

def run_server():
        config = json.loads(open(os.path.expanduser('~/.dppcv/config.json')).read())
	graphics = Graphics(config)
	print "Allowing exec-python: " + str(config.has_key('allow-exec-python'))
	server = SimpleWebSocketServer('', 8001, PrintServer)
        #server.serveforever()
	thread.start_new_thread(server.serveforever, tuple([{'graphics':graphics, 'config':config}]) )
        lt = time.time()*1000
        while True:
                t = time.time()*1000
                #server.serveonce()
		graphics.update(t-lt)
                lt = t
run_server()
