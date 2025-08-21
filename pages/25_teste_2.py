def excluir_linhas(rows: list[int]):
    """
    Exclui linhas no Google Sheets de forma robusta usando batch_update
    (deleteDimension). Agrupa linhas contíguas e executa de baixo pra cima.
    """
    if not rows:
        return 0

    ws, _ = _get_ws_and_headers()

    # Normaliza e ordena
    rows_sorted = sorted(set(int(r) for r in rows))

    # Agrupa em faixas contíguas: [(start, end), ...] (1-based)
    ranges = []
    start = end = None
    for r in rows_sorted:
        if start is None:
            start = end = r
        elif r == end + 1:
            end = r
        else:
            ranges.append((start, end))
            start = end = r
    if start is not None:
        ranges.append((start, end))

    # Monta requests deleteDimension (0-based, endIndex exclusivo)
    # Executa de baixo pra cima para não deslocar as linhas restantes
    requests = []
    for s, e in reversed(ranges):
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": ws.id,        # id numérico da aba
                    "dimension": "ROWS",
                    "startIndex": s - 1,     # 0-based inclusive
                    "endIndex": e            # 0-based exclusive
                }
            }
        })

    if requests:
        ws.spreadsheet.batch_update({"requests": requests})

    return len(rows_sorted)
