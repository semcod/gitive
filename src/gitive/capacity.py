"""Capacity arithmetic shared by future import planners; no disk mutation."""
def assess(free_bytes,twin_bytes,additional_bytes):
    """Additional allocation includes staging/downloads; reserve one twin copy."""
    values=(free_bytes,twin_bytes,additional_bytes)
    if any(type(v) is not int or v<0 for v in values):raise ValueError('Rozmiary muszą być nieujemnymi liczbami bajtów')
    required=twin_bytes+additional_bytes
    return {'fits':free_bytes>=required,'required_free_bytes':required,'shortfall_bytes':max(0,required-free_bytes)}
