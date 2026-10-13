#!/usr/bin/env python3
import binascii
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from visual_heartbeat import decode, validate_progress, FRAME_BYTES

def frame(record):
    buf=bytearray(FRAME_BYTES)
    for bit in range(384):
        color=0xf0 if record[bit//8]>>(bit%8)&1 else 0x10
        for dy,dx in ((3,3),(3,4),(4,3),(4,4)):
            at=((700+bit//64*8+dy)*1024+bit%64*8+dx)*4
            buf[at:at+3]=bytes([color])*3
    return buf

def record():
    data=struct.pack('<8sQQQII',b'LWP3HB01',123,7,7000,200,1)
    crc=binascii.crc32(data)
    return data+struct.pack('<II',crc,crc^0xffffffff)

def samples():
    return [dict(nonce='123',pid=200,version=1,sequence=i,tick_ms=i*2000,
                 received_monotonic=10+i*2) for i in range(21)]

class HeartbeatTests(unittest.TestCase):
    def test_decode(self):
        result=decode(frame(record()))
        self.assertEqual((result['sequence'],result['tick_ms'],result['pid']),(7,7000,200))
    def test_corruption(self):
        data=bytearray(record()); data[16]^=1
        with self.assertRaisesRegex(ValueError,'CRC'): decode(frame(data))
    def test_torn_cell(self):
        data=frame(record()); data[(703*1024+3)*4]=0
        with self.assertRaises(ValueError): decode(data)
    def test_black_frame(self):
        with self.assertRaises(ValueError): decode(bytes(FRAME_BYTES))
    def test_truncated(self):
        with self.assertRaises(ValueError): decode(bytes(100))
    def test_live(self):
        self.assertTrue(validate_progress(samples(),0,52,30)['passed'])
    def test_stale(self):
        rows=samples()
        for item in rows: item.update(sequence=1,tick_ms=2000)
        self.assertFalse(validate_progress(rows,0,52,30)['passed'])
    def test_replay(self):
        rows=samples(); rows[10]['sequence']=1
        self.assertFalse(validate_progress(rows,0,52,30)['passed'])
    def test_identity(self):
        rows=samples(); rows[-1]['nonce']='old'
        self.assertFalse(validate_progress(rows,0,52,30)['passed'])
    def test_tick_frozen(self):
        rows=samples(); rows[-1]['tick_ms']=rows[-2]['tick_ms']
        self.assertFalse(validate_progress(rows,0,52,30)['passed'])
    def test_long_gap(self):
        rows=samples(); del rows[5:10]
        self.assertFalse(validate_progress(rows,0,52,30)['passed'])
    def test_short_or_late(self):
        self.assertFalse(validate_progress(samples(),0,52,1800)['passed'])
        rows=samples()
        for row in rows: row['received_monotonic']+=100
        self.assertFalse(validate_progress(rows,0,152,30)['passed'])

if __name__=='__main__': unittest.main()
