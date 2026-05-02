def format_trade_output(stock_data):
    formatted = []

    for item in stock_data:
        formatted.append({
            "STOCK": item["stock"],
            "SIDE": item["side"],
            "STATUS": item["status"],
            "SOURCE": item["source"],
            "PRICE": item["price"],
            "ENTRY": item["entry"],
            "SL": item["sl"],
            "T1": item["t1"],
            "T2": item["t2"],
            "RR": item["rr"],
            "SCORE": item["score"],
            "REASON": item["reason"]
        })

    return formatted