#!/usr/bin/env python3

from binascii import hexlify
import sys
from time import sleep
from zag import *
from queue import Queue


class Coordinator(object):
    def __init__(self, port):
        self.device = Device(port)
        _, short = self.device.get_value(Device.Param.short_addr)
        _, ext = self.device.get_object(Device.Param.long_addr, 8)
        print('I\'m 0x%04X, %s' % (short, hexlify(ext).decode('utf8').upper()))

        self.device.set_value(Device.Param.channel, 11)
        self.device.set_value(Device.Param.rx_mode, 0)
        self.device.set_value(Device.Param.tx_mode, Device.TxMode.send_on_cca)

    def debug_object(self, o):
        l = []
        for k, v in vars(o).items():
            if isinstance(v, IntEnum):
                v = repr(v)
            elif isinstance(v, int):
                v = f'0x{v:X}'
            else:
                v = repr(v)
            l.append('%s:%s' % (k, v))
        s = str(type(o)) + ': '
        s += ', '.join(l)
        print(s)

    def debug_packet(self, packet):
        mhr, payload = MHR.decode(packet)
        self.debug_object(mhr)
        if mhr.frame_control & 0x7 == MHR.FrameType.beacon:
            beacon, payload = Beacon.decode(payload)
            self.debug_object(beacon)
        elif mhr.frame_control & 0x7 == MHR.FrameType.cmd:
            cmd, payload = Cmd.decode(payload)
            self.debug_object(cmd)
        if payload:
            print('payload:', payload)

    def button_handler(self, button):
        if button == 1:
            mhr = MHR()
            mhr.frame_control |= MHR.FrameType.cmd << MHR.FrameControl.type
            mhr.frame_control |= MHR.AddrMode.short << MHR.FrameControl.dst_mode
            mhr.dst_panid = 0xFFFF
            mhr.dst_addr = 0xFFFF
            packet = mhr.encode()

            cmd = Cmd()
            cmd.identifier = Cmd.Identifier.beacon_request
            packet += cmd.encode()

            self.device.send_packet(packet)

    def packet_handler(self, packet, rssi):
        self.debug_packet(packet)

    def loop(self):
        try:
            while True:
                event, data = self.device.event_queue.get()
                if event == Device.Event.on_packet:
                    self.packet_handler(*data)
                elif event == Device.Event.on_button:
                    self.button_handler(*data)
        except KeyboardInterrupt:
            self.device.shutdown()


if __name__ == '__main__':
    coordinator = Coordinator(sys.argv[1])
    coordinator.loop()
