#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import os
import sys
import time
import datetime
import argparse

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from luma.core import cmdline, error
from luma.core.render import canvas
from luma.core.sprite_system import framerate_regulator
from PIL import ImageFont


# Event handler for monitorstatus file update detection
class WatchDogEvent(FileSystemEventHandler):
    def __init__(self, filename):
        self.filename = filename
        self.modified = None

    def on_modified(self, event):
        if event.src_path == self.filename:
            self.modified = True

# Contains a icon or text label
class Label:
    def __init__(self, pocketlcd, font, text):
        self.pocketlcd = pocketlcd
        self.font = font
        self.text = text
        self.width = 0
        self.height = 0
        self.linedimensions = []
        for i, line in enumerate(self.text.split("\n")):
            w, h = self.calcdimensions(line.strip())
            self.linedimensions.append((w,h))
            self.height += h
            if w > self.width:
                self.width = w

    # Calulate dimensions of a rendered text or icon
    def calcdimensions(self, text):
        draw = self.pocketlcd.draw().__enter__() # we only want calculate, not display
        w, h = draw.textsize(text=text, font=self.font)
        del draw.draw # see render.py "tidy up resources"
        del draw
        return (w,h)

    # paint text or icon to display
    def paint(self, draw, pos):
        maxw = max([i[0] for i in self.linedimensions])
        height = 0
        for i, line in enumerate(self.text.split("\n")):
            draw.text((pos[0]+((maxw-self.linedimensions[i][0])/2), pos[1]+height), line, font=self.font, fill="white")
            height += self.linedimensions[i][1]

    # paint text or icon in the center of display
    def paintcenter(self, draw):
        x = (self.pocketlcd.lcd.width - self.width) / 2
        y = (self.pocketlcd.lcd.height - self.height) / 2
        self.paint(draw, (x,y))

    # paint text or icon to the top center of display
    def painttopcenter(self, draw, veroffset=0):
        x = (self.pocketlcd.lcd.width - self.width) / 2
        self.paint(draw, (x,veroffset))

    # paint text or icon to the bottom center of display
    def paintbottomcenter(self, draw, veroffset=0):
        x = (self.pocketlcd.lcd.width - self.width) / 2
        self.paint(draw, (x, self.pocketlcd.lcd.height-self.height-veroffset))

    # paint text or icon to the left center of display
    def paintmiddleleft(self, draw, horoffset=0):
        y = (self.pocketlcd.lcd.height - self.height) / 2
        self.paint(draw, (horoffset,y))


# Contains all informations for display drawing
class PocketLCD:
    def __init__(self, device):
        self.lcd = device
        self.label = {}
        self.fontsize = 10
        self.font = {}

    # Create a new label
    def newlabel(self, key, font, text, override=False):
        if override==True or key not in self.label:
            self.label[key] = Label(self, self.font[font], text)
        return self.label[key]

    # Create a display renderer
    def draw(self):
        return canvas(self.lcd)

    # Create a font instance
    def make_font(self, name, size=None):
        font_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), 'fonts', name))
        return ImageFont.truetype(font_path, self.fontsize if size is None else size)

# Draw display
def stats(args, lcd, obs):
    while True:
        obs.modified = False

        # read properties from cache file
        properties = {}
        try:
            with open(obs.filename) as fp:
                for line in fp:
                     parts = line.strip().split("\t")
                     pkey = parts[0].strip()
                     pval = parts[1].strip() if len(parts)>1 else ""
                     properties[pkey] = pval
            readfilesuccess = True
        except:
            print "Cannot open status file"
            with lcd.draw() as draw:
                lcd.newlabel("erropen", "text", "Cannot open file").paintcenter(draw)
            time.sleep(5)
            continue

        print "Debug: parse status file"
        print properties

        # prepare values
        batch = properties['CHARG_IND']
        perc = properties['BATT_PERCENT']
        wnet = properties['WIFI_NET']
        wip = properties['WIFI_IP']
        wanip = properties['WAN_IP']
        wanorg = properties['WAN_ORG']

        # battery icon
        fperc = float(perc[0:-1])

        batticon = ""
        if fperc >= 85:
            batticon = "iconbatt85" # full
        elif fperc >= 60:
            batticon = "iconbatt60" # 3/4
        elif fperc >= 40:
            batticon = "iconbatt40" # 1/2
        elif fperc >= 20:
            batticon = "iconbatt20" # 1/4
        else:
            batticon = "iconbatt0" # empty

        # display seach card with 0.15 frames per second
        regulator = framerate_regulator(fps=args.display_fps)

        while obs.modified == False:
            # time card
            if args.all_cards or args.card_time:
                with regulator:
                    with lcd.draw() as draw:
                        now = datetime.datetime.now()
                        t = now.strftime("%H:%M")
                        d = now.strftime("%Y-%m-%d")
                        lcd.newlabel("time"+t, "fstext", t).painttopcenter(draw)
                        lcd.newlabel("date"+d, "text", d).paintbottomcenter(draw)

            # battery card
            if args.all_cards or args.card_battery:
                with regulator:
                    with lcd.draw() as draw:
                        bi = lcd.label[batticon]
                        bt = lcd.newlabel("batttext"+perc, "fstext50", perc[0:-1]+"\n%")
                        pi = lcd.label['iconpower']
                        # batter with charge icon
                        if fperc<100 and batch == "1":
                            bt.paintmiddleleft(draw)
                            pi.paintmiddleleft(draw, bt.width+3)
                            bi.paintmiddleleft(draw, bt.width+3+pi.width+5)
                        # battery without charge icon
                        else:
                            bt.paintmiddleleft(draw, 10)
                            bi.paintmiddleleft(draw, 10+bt.width+10)

            # network card
            if args.all_cards or args.card_network:
                with regulator:
                    with lcd.draw() as draw:
                        # prepared icons
                        iconwifi = lcd.label["iconwifi"]
                        iconwip = lcd.label["iconwip"]
                        iconwan = lcd.label["iconwanip"]
                        iconwanorg = lcd.label["iconwanorg"]

                        # maximum with of all icons
                        maxiw = max([ iconwifi.width, iconwip.width, iconwan.width, iconwanorg.width ])
                        offset = maxiw+5

                        # current wifi network
                        i = 0
                        iconwifi.paint(draw, ((maxiw-iconwifi.width)/2,i))
                        lcd.newlabel("wnet"+wnet, "text", wnet).paint(draw, (offset, i))
                        # current wifi ip
                        i += iconwifi.height+1
                        iconwip.paint(draw, ((maxiw-iconwip.width)/2,i))
                        lcd.newlabel("wip"+wip, "text", wip).paint(draw, (offset, i))
                        # current wan ip
                        i += iconwip.height+1
                        iconwan.paint(draw, ((maxiw-iconwan.width)/2,i))
                        lcd.newlabel("wanip"+wanip, "text", wanip).paint(draw, (offset, i))
                        # current wan provider
                        i += iconwan.height+1
                        iconwanorg.paint(draw, ((maxiw-iconwanorg.width)/2,i))
                        lcd.newlabel("wanorg"+wanorg, "text", wanorg).paint(draw, (offset, i))

# Initialize lcd device, fonts and icons
def initlcd(args):
    # create device from arguments
    device = None
    try:
        device = cmdline.create_device(args)
    except error.Error as e:
        parser.error(e)

    # initialize pocketLCD container class
    lcd = PocketLCD(device)

    # font cache
    lcd.fontsize = 16
    lcd.font = {
        'icon': lcd.make_font('fontawesome-webfont.ttf'),
        'fsicon': lcd.make_font('fontawesome-webfont.ttf', lcd.lcd.height-10),
        'fsicon50': lcd.make_font('fontawesome-webfont.ttf', lcd.lcd.height/2),
        'text': lcd.make_font('C&C Red Alert [INET].ttf'),
        'fstext': lcd.make_font('C&C Red Alert [INET].ttf', lcd.lcd.height-10),
        'fstext50': lcd.make_font('C&C Red Alert [INET].ttf', lcd.lcd.height/2)
    }

    # icon cache
    lcd.newlabel("iconwifi", "icon", "\uf1eb")
    lcd.newlabel("iconwip", "icon", "\uf1e6")
    lcd.newlabel("iconwanip", "icon", "\uf0ac")
    lcd.newlabel("iconwanorg", "icon", "\uf1ad")
    lcd.newlabel("iconpower", "fsicon50", "\uf0e7")
    lcd.newlabel("iconbatt0", "fsicon", "\uf244")
    lcd.newlabel("iconbatt20", "fsicon", "\uf243")
    lcd.newlabel("iconbatt40", "fsicon", "\uf242")
    lcd.newlabel("iconbatt60", "fsicon", "\uf241")
    lcd.newlabel("iconbatt85", "fsicon", "\uf240")

    return lcd


# Run
def run():
    # create custom argument parser
    parser = cmdline.create_parser('PocketCHIP SysInfo')
    parser.add_argument('file', metavar='monitorstatus', type=str, help='sysinfo monitorstatus file')
    parser.add_argument('--display-fps', metavar='0.20', default=0.20, type=float, help='card change speed in fps')
    parser.add_argument('--all-cards', action='store_true', default=False, help='display all cards')
    parser.add_argument('--card-time', action='store_true', default=False, help='display the current time')
    parser.add_argument('--card-battery', action='store_true', default=False, help='display the battery info')
    parser.add_argument('--card-network', action='store_true', default=False, help='display the network info')
    args = parser.parse_args()

    # initialize status file observer
    statusfile = args.file
    observer = Observer()
    observerhandler = WatchDogEvent(statusfile)
    observer.schedule(observerhandler, os.path.dirname(statusfile), recursive=False)
    observer.start()

    # init lcd
    lcd = initlcd(args)

    # display stats
    try:
        stats(args, lcd, observerhandler)
    except KeyboardInterrupt:
        pass

    observer.stop()
    observer.join()


# Start program
if __name__ == "__main__":
    reload(sys)
    sys.setdefaultencoding('utf8')

    run()

