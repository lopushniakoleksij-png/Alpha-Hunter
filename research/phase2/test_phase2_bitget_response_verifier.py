import json
import unittest
from phase2_bitget_response_verifier import verify_response as v
START=1794096000000
def payload(rows,code="00000"):
    return json.dumps({"code":code,"requestTime":1794475212648,"data":rows}).encode()
def row(i):
    return [str(START+i*3600000),"100","110","90","105","10","1000"]
def check(rows,**kw):
    return v(payload(rows),symbol="BTCUSDT",start_ms=START,end_ms=START+3*3600000,**kw)
class ResponseTests(unittest.TestCase):
    def test_complete(self):self.assertEqual(check([row(i) for i in range(3)]).status,"PASS")
    def test_missing(self):self.assertEqual(check([row(0),row(1)]).reason,"INCOMPLETE_WINDOW")
    def test_duplicate(self):self.assertEqual(check([row(0),row(0),row(2)]).reason,"TIMESTAMP_GAP_OR_ORDER")
    def test_wrong_order(self):self.assertEqual(check([row(1),row(0),row(2)]).reason,"TIMESTAMP_GAP_OR_ORDER")
    def test_bad_ohlc(self):
        a=[row(i) for i in range(3)];a[1][2]="80"
        self.assertEqual(check(a).reason,"INVALID_OHLC")
    def test_nan(self):
        a=[row(i) for i in range(3)];a[1][1]="NaN"
        self.assertEqual(check(a).reason,"INVALID_OHLC")
    def test_wrong_market(self):self.assertEqual(check([row(i) for i in range(3)],product_type="SPOT").reason,"REQUEST_MARKET_NOT_ALLOWED")
    def test_api_failure(self):
        self.assertEqual(v(payload([row(0)],"400"),symbol="BTCUSDT",start_ms=START,end_ms=START+3600000).reason,"API_RESPONSE_FAILURE")
    def test_bad_json(self):
        self.assertEqual(v(b"broken",symbol="BTCUSDT",start_ms=START,end_ms=START+3600000).reason,"INVALID_JSON_OR_FIELDS")
    def test_hash(self):
        x=check([row(i) for i in range(3)])
        self.assertEqual(len(x.raw_sha256),64)
if __name__=="__main__":unittest.main()
