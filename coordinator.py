#!/usr/bin/env python3

from binascii import hexlify
from configparser import ConfigParser
import sys
from time import sleep
from zag import *
from queue import Queue
from random import randint


class Coordinator(object):
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
        self.panid = int(config.get('coordinator', 'panid', fallback='0x0000'), 0)
        self.services = [int(n) for n in config.get('coordinator', 'services', fallback='0').split(',')]
        self.services.sort()
        self.ssid = config.get('coordinator', 'ssid', fallback='Sample')

        self.bsn = randint(0, 255)
        self.dsn = randint(0, 255)

        self.dev.set_value(DEV.Param.channel, self.channel)
        self.dev.set_value(DEV.Param.rx_mode, 0)
        self.dev.set_value(DEV.Param.tx_mode, DEV.TxMode.send_on_cca)

    def cmd_handler(self, mhr, cmd, payload):
        if cmd.identifier == CMD.Identifier.bcn_request:
            self.bcn_request_handler(mhr, cmd)

    def bcn_request_handler(self, mhr, cmd):
        if mhr.frame_control >> MHR.FrameControl.src_mode & 0x3 != MHR.AddrMode.none:
            return
        if mhr.frame_control >> MHR.FrameControl.dst_mode & 0x3 != MHR.AddrMode.short:
            return
        if mhr.dst_panid != 0xFFFF:
            return
        if mhr.dst_addr != 0xFFFF:
            return
        self.send_bcn()

    def send_bcn(self):
        mhr = MHR()
        mhr.frame_control |= MHR.FrameType.bcn << MHR.FrameControl.type
        mhr.frame_control |= MHR.AddrMode.short << MHR.FrameControl.src_mode
        mhr.seq_num = self.bsn
        mhr.src_panid = self.panid
        _, mhr.src_addr = self.dev.get_value(DEV.Param.short_addr)
        packet = mhr.encode()

        bcn = BCN()
        bcn.superframe |= 15 << BCN.Superframe.bcn_order
        bcn.superframe |= 15 << BCN.Superframe.superframe_order
        bcn.superframe |= 1 << BCN.Superframe.pan_coordinator
        bcn.superframe |= 1 << BCN.Superframe.association_permit
        bcn.ssid = self.ssid
        bcn.services = self.services
        packet += bcn.encode()

        self.dev.send_packet(packet)
        self.bsn += 1

    def packet_handler(self, packet, rssi):
        debug_packet(packet)

        mhr, payload = MHR.decode(packet)
        if mhr.frame_control & 0x7 == MHR.FrameType.cmd:
            cmd, payload = CMD.decode(payload)
            self.cmd_handler(mhr, cmd, payload)

    def button_handler(self, button):
        self.dev.set_leds(1<<button, ~self.dev.get_leds() & 0xFF)

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
    coordinator = Coordinator(sys.argv[1])
    coordinator.loop()
