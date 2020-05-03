#!/usr/bin/env python3

from binascii import hexlify
from configparser import ConfigParser
import sys
from time import sleep
from zag import *
from queue import Queue
from random import randint

class Device(object):
    def __init__(self, port):
        self.dev = DEV(port)
        _, short = self.dev.get_value(DEV.Param.short_addr)
        _, ext = self.dev.get_object(DEV.Param.long_addr, 8)
        print('I\'m 0x%04X, %s' % (short, hexlify(ext).decode('utf8').upper()))

        with open('config.ini', 'r') as f:
            config_string = '[DEFAULT]\n' + f.read()
        config = ConfigParser()
        config.read_string(config_string)
        self.channel = int(config.get('DEFAULT', 'channel', fallback='11'))

        self.dsn = randint(0, 255)

        self.dev.set_value(DEV.Param.channel, self.channel)
        self.dev.set_value(DEV.Param.rx_mode, 0)
        self.dev.set_value(DEV.Param.tx_mode, DEV.TxMode.send_on_cca)

    def button_handler(self, button):
        if button == 1:
            mhr = MHR()
            mhr.frame_control |= MHR.FrameType.cmd << MHR.FrameControl.type
            mhr.frame_control |= MHR.AddrMode.short << MHR.FrameControl.dst_mode
            mhr.seq_num = self.dsn
            mhr.dst_panid = 0xFFFF
            mhr.dst_addr = 0xFFFF
            packet = mhr.encode()

            cmd = CMD()
            cmd.identifier = CMD.Identifier.bcn_request
            packet += cmd.encode()

            self.dev.send_packet(packet)
            self.dsn += 1

    def packet_handler(self, packet, rssi):
        debug_packet(packet)

    def loop(self):
        try:
            while True:
                event, data = self.dev.event_queue.get()
                if event == DEV.Event.on_packet:
                    self.packet_handler(*data)
                elif event == DEV.Event.on_button:
                    self.button_handler(*data)
        except KeyboardInterrupt:
            self.dev.shutdown()


if __name__ == '__main__':
    coordinator = Device(sys.argv[1])
    coordinator.loop()
