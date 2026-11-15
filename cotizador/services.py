"""Motor de cálculo COMEX (misma lógica del prototipo, ahora en el servidor)."""
import math

from .constants import (
    MAX_TON_CONT, TASA_ARANCEL, TASA_IVA, TRAMOS_CONTINGENCIA_DEFECTO,
)
from .models import TramoContingencia


def cargar_tramos():
    """Lista [(dias_hasta | None, fracción)] ordenada; usa los valores por defecto si la tabla está vacía."""
    tramos = [(t.dias_hasta, float(t.porcentaje) / 100) for t in TramoContingencia.objects.all()]
    if not tramos:
        tramos = [(d, p / 100) for d, p in TRAMOS_CONTINGENCIA_DEFECTO]
    return tramos


def pct_contingencia(dias, tramos):
    for dias_hasta, fraccion in tramos:
        if dias_hasta is not None and dias <= dias_hasta:
            return fraccion
    for dias_hasta, fraccion in tramos:
        if dias_hasta is None:
            return fraccion
    return tramos[-1][1]      # sin tramo abierto: se usa el último


def calcular(tarifa, toneladas, contenedores, fob, dias, tlc, tc, tramos=None):
    tramos = tramos if tramos is not None else cargar_tramos()
    sugeridos = math.ceil(toneladas / MAX_TON_CONT) if toneladas > 0 else 0
    cont_usados = contenedores if contenedores > 0 else sugeridos
    cantidad = cont_usados if tarifa.cobro == "contenedor" else toneladas

    flete_base = float(tarifa.monto) * cantidad
    pct_cont = pct_contingencia(dias, tramos)
    recargo = flete_base * pct_cont
    flete_total = flete_base + recargo
    seguro = 0                                   # exento por póliza global CINTAC
    cif = fob + flete_total + seguro
    pct_arancel = 0 if tlc else TASA_ARANCEL
    arancel = cif * pct_arancel
    iva = cif * TASA_IVA                         # 19% sobre valor CIF
    total_usd = cif + arancel + iva

    return {
        "toneladas": toneladas, "sugeridos": sugeridos, "contUsados": cont_usados,
        "cantidad": cantidad, "fob": fob, "dias": dias, "tlc": bool(tlc), "tc": tc,
        "fleteBase": flete_base, "pctCont": pct_cont, "recargo": recargo,
        "fleteTotal": flete_total, "seguro": seguro, "cif": cif,
        "pctArancel": pct_arancel, "arancel": arancel, "iva": iva,
        "totalUSD": total_usd, "totalCLP": total_usd * tc,
        "tonPorCont": toneladas / cont_usados if cont_usados > 0 else 0,
    }
