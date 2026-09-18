from app.services.market_data_ingestion.providers.nse_delivery import NseDeliveryProvider


def test_parse_bhav_minimal():
    csv_text = "SYMBOL,SERIES,TTL_TRD_QNTY,DELIV_QTY\nRELIANCE,EQ,1000,400\n"
    p = NseDeliveryProvider()
    m = p._parse_bhav_csv(csv_text)
    rec = p.lookup(m, symbol="RELIANCE-EQ")
    assert rec is not None
    assert rec["delivery_qty"] == 400
    assert rec["traded_qty"] == 1000
    assert rec["delivery_pct"] == 40.0


def test_parse_sec_bhav_spaced_headers():
    csv_text = (
        "SYMBOL, SERIES, DATE1, TTL_TRD_QNTY, DELIV_QTY, DELIV_PER\n"
        "RELIANCE, EQ, 07-Aug-2026, 9885638, 5187857, 52.48\n"
    )
    p = NseDeliveryProvider()
    m = p._parse_bhav_csv(csv_text)
    rec = p.lookup(m, symbol="RELIANCE")
    assert rec is not None
    assert rec["delivery_qty"] == 5187857
    assert abs(float(rec["delivery_pct"]) - 52.48) < 0.01


def test_parse_mto_reliance():
    text = (
        "Security Wise Delivery Position - Compulsory Rolling Settlement\n"
        "10,MTO,07082026,1549728086,0003154\n"
        "Trade Date <07-AUG-2026>,Settlement Type <N>\n"
        "Record Type,Sr No,Name of Security,Quantity Traded,"
        "Deliverable Quantity(gross across client level),% of Deliverable Quantity to Traded Quantity\n"
        "20,2342,RELIANCE,EQ,9885638,5187857,52.48\n"
        "20,1,0SCL27,YW,3,3,100.00\n"
    )
    p = NseDeliveryProvider()
    m = p._parse_mto(text)
    rec = p.lookup(m, symbol="RELIANCE-EQ")
    assert rec is not None
    assert rec["delivery_qty"] == 5187857
    assert rec["traded_qty"] == 9885638
    assert abs(float(rec["delivery_pct"]) - 52.48) < 0.01
    # Non-EQ series skipped
    assert p.lookup(m, symbol="0SCL27") is None


def test_malformed_rows_skipped():
    csv_text = "SYMBOL,SERIES\nFOO,EQ\n"
    p = NseDeliveryProvider()
    m = p._parse_bhav_csv(csv_text)
    rec = p.lookup(m, symbol="FOO-EQ")
    # No delivery columns → empty map or no usable rec
    assert rec is None or rec.get("delivery_pct") is None
