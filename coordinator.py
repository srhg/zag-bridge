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

    def cmd_handler(self, mhr, cmd, payload):
        if cmd.identifier == Cmd.Identifier.beacon_request:
            self.beacon_request_handler(mhr, cmd)

    def beacon_request_handler(self, mhr, cmd):
        if mhr.frame_control >> MHR.FrameControl.src_mode & 0x3 != MHR.AddrMode.none:
            return
        if mhr.frame_control >> MHR.FrameControl.dst_mode & 0x3 != MHR.AddrMode.short:
            return
        if mhr.dst_panid != 0xFFFF:
            return
        if mhr.dst_addr != 0xFFFF:
            return
        self.send_beacon()

    def send_beacon(self):
        mhr = MHR()
        mhr.frame_control |= MHR.FrameType.beacon << MHR.FrameControl.type
        mhr.frame_control |= MHR.AddrMode.short << MHR.FrameControl.src_mode
        mhr.src_panid = 0xBEEF
        _, mhr.src_addr = self.device.get_value(Device.Param.short_addr)
        packet = mhr.encode()

        beacon = Beacon()
        beacon.superframe |= 15 << Beacon.Superframe.beacon_order
        beacon.superframe |= 15 << Beacon.Superframe.superframe_order
        beacon.superframe |= 1 << Beacon.Superframe.pan_coordinator
        beacon.superframe |= 1 << Beacon.Superframe.association_permit
        packet += beacon.encode()

        self.device.send_packet(packet)

    def packet_handler(self, packet, rssi):
        debug_packet(packet)

        mhr, payload = MHR.decode(packet)
        if mhr.frame_control & 0x7 == MHR.FrameType.cmd:
            cmd, payload = Cmd.decode(payload)
            self.cmd_handler(mhr, cmd, payload)

    def button_handler(self, button):
        self.device.set_leds(1<<button, ~self.device.get_leds() & 0xFF)

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
