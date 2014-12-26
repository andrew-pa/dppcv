#!/usr/bin/python2

import os
import sys
import StringIO
import thread
from printcore import *
import pygame
from pygame.locals import *
from swss import *
import simplejson as json
import xml.etree.ElementTree as xml
import base64
import zipfile
import png
import time
from print_server import *


class Graphics():
    def __init__(self, conf):
        self.cf = conf
        self.profile = xml.parse(os.path.expanduser('~/.dppcv/')+self.cf['profile-path'])
        self.printing = False
        self.paused = False
        self.current_layer = -1
        self.layer_timer = 0
        self.printer = None
        pygame.init()
        self.dipsurf = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN | pygame.NOFRAME)
        pygame.display.set_caption('DPPCV display')
        self.current_layer_image = None
        self.print_file = None

    def initprintcore(self, port, baudrate):
        self.printer = printcore(port, baudrate)

    def pause(self):
        self.paused = True
    def resume(self):
        self.paused = False

    #assumes that current_layer is the layer to load
    def get_next_layer(self):
        pygame.image.load(os.path.expanduser('~/.dppcv/tmp/')+self.print_file[1] + str(self.current_layer).rjust(4, '0') + '.png')

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

    def start_print(self, f):
        self.print_file = f
        self.print_file[0].extractall(os.path.expanduser('~/.dppcv/tmp/'))
        self.current_layer = 0
        self.printing = True
        self.paused = False
        self.layer_timer = float(self.profile.find('InkConfig').find('LayerTime').text)
        self.process_gcode(self.profile.find('GCodeHeader').text)
        self.get_next_layer()

    def update(self, dt):
        if self.printing and not self.paused:
            self.layer_timer -= dt
            if self.layer_timer <= 0:
                self.current_layer = self.current_layer + 1
                print "Next Layer: " + str(self.current_layer)
                if self.current_layer > len(self.layers):
                    self.process_gcode(self.profile.find('GCodeFooter').text)
                    self.current_layer = -1
                    self.printing = False
                    os.remove(os.expanduser('~/.dppcv/tmp/'))
                    return
                self.get_next_layer()
                self.layer_timer=float(self.profile.find('InkConfig').find('LayerTime').text)
                self.process_gcode(self.profile.find('GCodeLift').text)
                #while not self.printer.clear:
                    #pass
        self.dipsurf.fill((0,0,0))
        if self.printing and not self.paused:
            self.dipsurf.blit(self.current_layer_image, 0,0)
        #deal with pygame events
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()

        pygame.display.update()


def run_server():
    config = json.loads(open(os.path.expanduser('~/.dppcv/config.json')).read())
    graphics = Graphics(config)
    print "Allowing exec-python: " + str(config.has_key('allow-exec-python'))
    server = SimpleWebSocketServer('', 8001, PrintServer)
    thread.start_new_thread(server.serveforever, tuple([{'graphics':graphics, 'config':config}]) )
    lt = time.time()*1000
    while True:
        t = time.time()*1000
        graphics.update(t-lt)
        lt = t
run_server()
