#!/usr/bin/env python3

from enum import IntEnum, IntFlag, unique
from queue import Queue
import random
from serial import Serial
import struct
from threading import Thread

__all__ = ['DEV', 'MHR', 'BCN', 'CMD', 'debug_packet']

class DEV(object):
    header_struct = struct.Struct('!BB')

    @unique
    class Request(IntEnum):
        send_packet = 0
        get_mem     = 1
        set_mem     = 2
        get_mem_rev = 3
        set_mem_rev = 4
        get_value   = 5
        set_value   = 6
        get_object  = 7
        set_object  = 8
        get_leds    = 9
        set_leds    = 10

        def __str__(self):
            return str(self.name)

    @unique
    class Response(IntEnum):
        ok  = 128
        err = 129

        def __str__(self):
            return str(self.name)

    @unique
    class Event(IntEnum):
        on_packet = 192
        on_button = 193

        def __str__(self):
            return str(self.name)

    class ResponseErr(Exception):
        pass

    @unique
    class Result(IntEnum):
        ok            = 0
        not_supported = 1
        invalid_value = 2
        error         = 3

        def __str__(self):
            return str(self.name)

    @unique
    class TransmitResult(IntEnum):
        ok        = 0
        drr       = 1
        collision = 2
        no_ack    = 3

        def __str__(self):
            return str(self.name)

    @unique
    class Param(IntEnum):
        power_mode            = 0
        channel               = 1
        pan_id                = 2
        short_addr            = 3
        rx_mode               = 4
        tx_mode               = 5
        tx_power              = 6
        cca_threshold         = 7
        rssi                  = 8
        last_rssi             = 9
        last_link_quality     = 10
        long_addr             = 11
        last_packet_timestamp = 12
        # Constants
        channel_min           = 13
        channel_max           = 14
        txpower_min           = 15
        txpower_max           = 16

        def __str__(self):
            return str(self.name)

    @unique
    class RxMode(IntFlag):
        address_filter = 1
        auto_ack       = 2
        poll_mode      = 4

    @unique
    class TxMode(IntFlag):
        send_on_cca = 1

    def __init__(self, port):
        self.serial = Serial(port, timeout=0.1)
        self.serial.write(b'\xAAZAG')
        self.do_sync = True
        self.serial.flush()
        self.reader_queue = Queue()
        self.event_queue = Queue()
        self.thread = Thread(target=self.reader)
        self.thread.start()

    def shutdown(self):
        self.done = True

    def reader(self):
        self.done = False
        while not self.done:
            if self.do_sync:
                data = self.serial.read_until(b'\xAAZAG')
                if not data:
                    self.serial.write(b'\xAAZAG')
                    continue
                elif not data.endswith(b'\xAAZAG'):
                    continue
                self.do_sync = False

            data = self.serial.read(DEV.header_struct.size)
            if len(data) != DEV.header_struct.size:
                continue
            response, data_len = DEV.header_struct.unpack(data)

            data = self.serial.read(data_len)
            if len(data) != data_len:
                continue

            if response & 0xC0 == 0xC0:
                event = DEV.Event(response)
                if event == DEV.Event.on_packet:
                    rssi, link_quality = struct.unpack('!bB', data[-2:])
                    data = (data[:-2], rssi)
                elif event == DEV.Event.on_button:
                    data = struct.unpack('!B', data)
                self.event_queue.put((event, data))
                continue

            response = DEV.Response(response)
            self.reader_queue.put((response, data))

    def write(self, cmd, data=b''):
        packet = DEV.header_struct.pack(cmd.value, len(data)) + data
        self.serial.write(packet)
        response, data = self.reader_queue.get()
        if response == DEV.Response.err:
            raise DEV.ResponseErr
        return data

    def send_packet(self, data):
        data = self.write(DEV.Request.send_packet, data)
        result, = struct.unpack('!H', data)
        result = DEV.TransmitResult(result)
        return result,

    def get_mem(self, addr, n=1, reverse=False):
        data = struct.pack('!HB', int(addr), int(n))
        if reverse:
            data = self.write(DEV.Request.get_mem_rev, data)
        else:
            data = self.write(DEV.Request.get_mem, data)
        if n == 1:
            data = data[0]
        return data

    def set_mem(self, addr, data, reverse=False):
        if isinstance(data, int):
            data = struct.pack('!HB', int(addr), data)
        else:
            data = struct.pack('!H', int(addr)) + data
        if reverse:
            self.write(DEV.Request.set_mem_rev, data)
        else:
            self.write(DEV.Request.set_mem, data)

    def get_value(self, param):
        data = struct.pack('!H', int(param))
        data = self.write(DEV.Request.get_value, data)
        result, value = struct.unpack('!HH', data)
        result = DEV.Result(result)
        return result, value

    def set_value(self, param, value):
        data = struct.pack('!HH', int(param), value)
        data = self.write(DEV.Request.set_value, data)
        result, = struct.unpack('!H', data)
        result = DEV.Result(result)
        return result,
    
    def get_object(self, param, expected_len):
        data = struct.pack('!HB', int(param), expected_len)
        data = self.write(DEV.Request.get_object, data)
        result, = struct.unpack('!H', data[:2])
        result = DEV.Result(result)
        return result, data[2:]

    def set_object(self, param, data):
        data = struct.pack('!HH', int(param), len(data)) + data
        data = self.write(DEV.Request.set_object, data)
        result, = struct.unpack('!H', data)
        result = DEV.Result(result)
        return result,

    def get_leds(self):
        data = self.write(DEV.Request.get_leds)
        leds, = struct.unpack('!B', data)
        return leds

    def set_leds(self, mask, values):
        data = struct.pack('!BB', int(mask), int(values))
        self.write(DEV.Request.set_leds, data)
        return True

class MHR(object):
    @unique
    class FrameControl(IntEnum):
        type = 0
        security = 3
        pending = 4
        req_ack = 5
        panid_compression = 6
        dst_mode = 10
        version = 12
        src_mode = 14

        def __str__(self):
            return str(self.name)

    @unique
    class FrameType(IntEnum):
        bcn          = 0
        data         = 1
        ack          = 2
        cmd          = 3
        multipurpose = 5
        fragment     = 6
        extended     = 7

        def __str__(self):
            return str(self.name)

    @unique
    class AddrMode(IntEnum):
        none  = 0
        short = 2
        long  = 3

        def __str__(self):
            return str(self.name)

    @unique
    class Version(IntEnum):
        version_2003 = 0
        version_2006 = 1
        version_2015 = 2
        reserved     = 3

        def __str__(self):
            return str(self.name)

    @classmethod
    def decode(cls, data):
        mhr = cls()

        offset = 0
        mhr.frame_control, mhr.seq_num = struct.unpack_from('!HB', data, offset)
        if (mhr.frame_control >> MHR.FrameControl.version) & 0x3 > MHR.Version.version_2006:
            return
        offset += 3

        dst_mode = MHR.AddrMode((mhr.frame_control >> MHR.FrameControl.dst_mode) & 0x3)

        if dst_mode in [MHR.AddrMode.short, MHR.AddrMode.long]:
            mhr.dst_panid, = struct.unpack_from('!H', data, offset)
            offset += 2

        if dst_mode == MHR.AddrMode.short:
            mhr.dst_addr, = struct.unpack_from('!H', data, offset)
            offset += 2
        elif dst_mode == MHR.AddrMode.long:
            mhr.dst_addr = data[offset:offset + 8]
            offset += 8

        src_mode = MHR.AddrMode((mhr.frame_control >> MHR.FrameControl.src_mode) & 0x3)
        
        panid_compression = (mhr.frame_control >> MHR.FrameControl.panid_compression) & 1
        if src_mode in [MHR.AddrMode.short, MHR.AddrMode.long]:
            if panid_compression and dst_mode in [MHR.AddrMode.short, MHR.AddrMode.long]:
                mhr.src_panid = mhr.dst_panid
            else:
                mhr.src_panid, = struct.unpack_from('!H', data, offset)
                offset += 2
       
        if src_mode == MHR.AddrMode.short:
            mhr.src_addr, = struct.unpack_from('!H', data, offset)
            offset += 2
        elif src_mode == MHR.AddrMode.long:
            mhr.src_addr = data[offset:offset + 8]
            offset += 8

        return mhr, data[offset:]

    def __init__(self):
        self.frame_control = 0
        self.seq_num = 0

    def encode(self):
        data = struct.pack('!HB', self.frame_control, self.seq_num)

        dst_mode = MHR.AddrMode((self.frame_control >> MHR.FrameControl.dst_mode) & 0x3)
    
        if dst_mode in [MHR.AddrMode.short, MHR.AddrMode.long]:
            data += struct.pack('!H', self.dst_panid)
        
        if dst_mode == MHR.AddrMode.short:
            data += struct.pack('!H', self.dst_addr)
        elif dst_mode == MHR.AddrMode.long:
            data += self.dst_addr
        
        src_mode = MHR.AddrMode((self.frame_control >> MHR.FrameControl.src_mode) & 0x3)

        panid_compression = (self.frame_control >> MHR.FrameControl.panid_compression) & 1
        if src_mode in [MHR.AddrMode.short, MHR.AddrMode.long] and not panid_compression:
            data += struct.pack('!H', self.src_panid)

        if src_mode == MHR.AddrMode.short:
            data += struct.pack('!H', self.src_addr)
        elif src_mode == MHR.AddrMode.long:
            data += self.src_addr
        
        return data

class BCN(object):
    @unique
    class Superframe(IntEnum):
        bcn_order          = 0
        superframe_order   = 4
        final_cap_slot     = 8
        ble                = 12
        pan_coordinator    = 14
        association_permit = 15

        def __str__(self):
            return str(self.name)

    @unique
    class GtsSpec(IntEnum):
        desc_count = 0
        permit     = 7

        def __str__(self):
            return str(self.name)

    @unique
    class GtsDirections(IntEnum):
        dir_mask = 0

        def __str__(self):
            return str(self.name)

    @unique
    class GtsDescriptor(IntEnum):
        short_addr = 0
        start_slot = 16
        gts_length = 20

        def __str__(self):
            return str(self.name)

    @classmethod
    def decode(cls, data):
        bcn = cls()

        offset = 0
        bcn.superframe, bcn.gts_spec = struct.unpack_from('!HB', data, offset)
        num_desc = bcn.gts_spec & 0x3
        offset += 3

        if (num_desc > 0):
            bcn.gts_mask, = struct.unpack_from('!B', data, offset)
            offset += 1

            bcn.gts_desc = []
            for _ in range(num_desc):
                short_addr, gts_info = struct.unpack_from('!HB', data, offset)
                desc = gts_info << 16 | short_addr
                bcn.gts_desc.append(desc)
                offset += 3

        pend_addr_spec, = struct.unpack_from('!B', data, offset)
        offset += 1

        bcn.pend_addr = []
        num_short = pend_addr_spec & 7
        for _ in range(pend_addr_spec & 7):
            short_addr, = struct.unpack_from('!H', data, offset)
            bcn.pend_addr.append(short_addr)
            offset += 2

        num_long = (pend_addr_spec >> 4) & 7
        for _ in range(num_long):
            long_addr = data[offset:offset + 8]
            bcn.pend_addr.append(long_addr)
            offset += 8

        magic = data[offset:offset + 4]
        if magic != b'Zag!':
            return bcn, data[offset:]
        offset += 4

        ssid_len, = struct.unpack_from('!B',data, offset)
        offset += 1
        ssid = data[offset:offset + ssid_len]
        bcn.ssid = ssid.decode('utf8')
        offset += ssid_len

        num_services, = struct.unpack_from('!B', data, offset)
        offset += 1
        for _ in range(num_services):
            service, = struct.unpack_from('!H', data, offset)
            bcn.services.append(service)
            offset += 2

        return bcn, data[offset:]

    def __init__(self):
        self.superframe = 0
        self.gts_spec = 0
        self.pend_addr = []
        self.ssid = b''
        self.services = []

    def encode(self):
        data = struct.pack('!HB', self.superframe, self.gts_spec)
        num_desc = self.gts_spec & 0x3
        if (num_desc > 0):
            data += struct.pack('!B', self.gts_mask)
            for i in range(num_desc):
                desc = self.gts_desc[i]
                data += struct.pack('!HB', desc & 0xFFFF, desc >> 16)

        short_addr, long_addr = [], []
        for addr in self.pend_addr:
            if isinstance(addr, int):
                short_addr.append(addr)
            elif isinstance(addr, bytes):
                long_addr.append(addr)
        
        data += struct.pack('!B', (len(long_addr) << 4) | len(short_addr))
        for addr in short_addr:
            data += struct.pack('!H', addr)
        
        for addr in long_addr:
            data += long_addr

        data += b'Zag!'

        ssid = self.ssid.encode('utf8')
        data += struct.pack('!B', len(ssid))
        data += ssid

        data += struct.pack('!B', len(self.services))
        for service in self.services:
            data += struct.pack('!H', service)

        return data

class CMD(object):
    @unique
    class Identifier(IntEnum):
        association_request         = 1
        association_response        = 2
        disassociation_notification = 3
        data_request                = 4
        panid_conflict              = 5
        orphan_notification         = 6
        bcn_request              = 7
        coordinator_realignment     = 8
        gts_request                 = 9

        def __str__(self):
            return str(self.name)

    class AssocCapability(IntEnum):
        alt_coordinator = 0
        dev_type = 1
        power_source = 2
        idle_recv = 3
        security = 6
        allocate_address = 7

        def __str__(self):
            return str(self.name)

    class AssocStatus(IntEnum):
        assoc_success = 0
        pan_at_capacity = 1
        access_denied = 2

        def __str__(self):
            return str(self.name)

    class DisassocReason(IntEnum):
        coord_leave = 1
        dev_leave = 2

        def __str__(self):
            return str(self.name)

    class GtsCharacteristics(IntEnum):
        length = 0
        direction = 4
        char_type = 5

        def __str__(self):
            return str(self.name)

    @classmethod
    def decode(cls, data):
        cmd = cls()

        offset = 0
        identifier, = struct.unpack_from('!B', data, offset)
        cmd.identifier = CMD.Identifier(identifier)
        offset += 1

        if cmd.identifier == CMD.Identifier.association_request:
            cmd.capability, = struct.unpack_from('!B', data, offset)
            offset += 1
        elif cmd.identifier == CMD.Identifier.association_response:
            cmd.short_addr, cmd.status = struct.unpack_from('!HB', data, offset)
            offset += 3
        elif cmd.identifier == CMD.Identifier.disassociation_notification:
            cmd.reason, = struct.unpack_from('!B', data, offset)
            offset += 1
        elif cmd.identifier == CMD.Identifier.coordinator_realignment:
            cmd.panid, cmd.coord_addr, cmd.channel, cmd.short_addr = struct.unpack_from('!HHBH', data, offset)
            offset += 7
        elif cmd.identifier == CMD.Identifier.gts_request:
            cmd.characteristics == struct.unpack_from('!B', data, offset)
            offset += 1

        return cmd, data[offset:]

    def __init__(self):
        self.capability = 0
        self.short_addr = None
        self.status = 0
        self.reason = 0
        self.panid = 0
        self.coord_addr = 0
        self.channel = 0
        self.characteristics = 0

    def encode(self):
        data = struct.pack('!B', self.identifier)
        if self.identifier == CMD.Identifier.association_request:
            data += struct.pack('!B', self.capability)
        elif self.identifier == CMD.Identifier.association_response:
            data += struct.pack('!HB', self.short_addr, self.status)
        elif self.identifier == CMD.Identifier.disassociation_notification:
            data += struct.pack('!B', self.reason)
        elif self.identifier == CMD.Identifier.coordinator_realignment:
            data += struct.pack('!HHBH', self.panid, self.coord_addr, self.channel, self.short_addr)
        elif self.identifier == CMD.Identifier.gts_request:
            data += struct.pack('!B', self.characteristics)

        return data

def debug_object(o):
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

def debug_packet(packet):
    mhr, payload = MHR.decode(packet)
    debug_object(mhr)
    if mhr.frame_control & 0x7 == MHR.FrameType.bcn:
        bcn, payload = BCN.decode(payload)
        debug_object(bcn)
    elif mhr.frame_control & 0x7 == MHR.FrameType.cmd:
        cmd, payload = CMD.decode(payload)
        debug_object(cmd)
    if payload:
        print('payload:', payload)
