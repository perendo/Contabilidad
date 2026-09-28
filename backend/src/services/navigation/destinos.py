"""Catalogo canonico de destinos de navegacion (SPEC-031, US4).

POR QUE HAY UNA COPIA EN EL BACKEND

`surfaces.ts` es la fuente de verdad y se despliega con la aplicacion (contrato,
seccion 4: "el mapa de superficies es frontend"). Pero el backend necesita conocer las
claves por dos razones que no admiten respuesta diferida al cliente:

1. `PUT /api/v1/favoritos/{destino}` debe rechazar con **404** un destino inexistente.
   Sin catalogo, "destino desconocido" y "el cliente tiene una errata en la clave" serian
   la misma respuesta, y el favorito se guardaria igual: una fila que ninguna superficie
   puede abrir y que el usuario tampoco puede quitar.
2. `GET /api/v1/favoritos` debe marcar `accesible: false` y `desconocido: true` en los
   que ya no existen (FR-024), conservandolos pero sin mostrarlos. Sin catalogo, el
   servidor no puede distinguir "destino real sin permiso" de "ruta reubicada".

QUE IMPIDE QUE LAS DOS COPIAS SE SEPAREN

`tests/unit/test_destinos_en_sync.py` compara este conjunto con las claves que extrae de
`surfaces.ts` y falla si se separan. Ese test es la parte importante de este fichero: sin
el, este conjunto seria una lista que se pudre en silencio. El reparto es: una clave nueva
se anade aqui **y** en `surfaces.ts`, en el mismo commit, y el test avisa si se ha hecho
solo a medias.

GENERADO, NO ESCRITO A MANO

Las claves las extrae `surfaces.ts` con un script de mantenimiento. Reejecutar tras anadir
un destino.
"""

from __future__ import annotations

#: Todas las claves de destino: el valor de `Destino.clave` en `surfaces.ts`.
DESTINOS: frozenset[str] = frozenset(
    {
        "alertas-liquidez",
        "anticipos",
        "anticipos-detalle",
        "anticipos-nuevo",
        "antiguedad",
        "apertura",
        "asientos",
        "asientos-detalle",
        "asientos-nuevo",
        "balance",
        "catalogo",
        "catalogo-detalle",
        "catalogo-importar",
        "catalogo-reclasificar",
        "centros-coste",
        "centros-nuevo",
        "cesiones",
        "cesiones-detalle",
        "cesiones-nueva",
        "cierre-anual",
        "cierre-ejercicio",
        "cierre-intermedio",
        "cierres-detalle",
        "cobros-detalle",
        "conciliacion",
        "conciliacion-detalle",
        "conciliacion-importar",
        "conciliacion-periodos",
        "condiciones-pago",
        "coste",
        "cuentas-anuales",
        "devoluciones",
        "devoluciones-detalle",
        "divisas",
        "divisas-asiento",
        "divisas-historial",
        "divisas-tipos",
        "divisas-valoracion",
        "documentos",
        "efectos",
        "efectos-detalle",
        "efectos-nuevo",
        "ejercicio",
        "empresas",
        "empresas-nueva",
        "exportaciones",
        "exportaciones-detalle",
        "exportaciones-nueva",
        "facturas",
        "facturas-detalle",
        "facturas-nueva",
        "facturas-rectificar",
        "flujos-efectivo",
        "import-export",
        "impuesto-sociedades",
        "informe-efe",
        "inmovilizado",
        "inmovilizado-alta",
        "inmovilizado-amortizaciones",
        "inmovilizado-detalle",
        "is-detalle",
        "is-nueva",
        "libros-iva",
        "mayor",
        "medios-pago",
        "modelo-190",
        "modelo-200",
        "modelos",
        "ong-caja",
        "ong-caja-detalle",
        "ong-libros",
        "ong-subvenciones",
        "ong-subvenciones-detalle",
        "permisos",
        "permisos-auditoria",
        "plan-cuentas",
        "plan-cuentas-nueva",
        "plantillas",
        "plantillas-detalle",
        "plantillas-generar",
        "plantillas-nueva",
        "presupuestos",
        "presupuestos-informes",
        "presupuestos-seguimiento",
        "previsiones",
        "previsiones-detalle",
        "pyg",
        "reaperturas",
        "remesas",
        "remesas-detalle",
        "remesas-nueva",
        "retenciones",
        "retenciones-detalle",
        "retenciones-nueva",
        "series",
        "sumas-saldos",
        "terceros",
        "terceros-detalle",
        "terceros-nuevo",
        "vencimientos",
    }
)

#: Maximo de favoritos visibles (FR-025). El recorte ocurre en la lectura, nunca en la
#: escritura: un rechazo al sexto dejaria al usuario con cinco sin poder anadir el suyo.
MAXIMO_VISIBLES = 5


PERMISO_POR_DEFECTO: tuple[str, str] = ("acct", "ver")


def es_conocido(destino: str) -> bool:
    """Si la clave existe en el mapa de superficies.

    Las entradas `{ ajuste: true }` NO están en `DESTINOS`: son ajustes del panel sin
    ruta, y un favorito sobre una de ellas sería un enlace a la nada. El generador las
    excluye al leer `surfaces.ts`, que es donde el mapa lo declara de forma explícita.
    """
    return destino in DESTINOS


def es_accesible(destino: str, concedidos: set[tuple[str, str]] | None) -> bool:
    """Si el usuario puede llegar a este destino.

    Un destino que no esta en el mapa **nunca** es accesible, aunque el usuario tenga
    todos los permisos: la clave guardada apunto a una ruta que ya no existe, y por eso
    va marcada `desconocido` y se conserva (FR-024), no se muestra.

    `concedidos` es el conjunto de `(modulo, operacion)` del usuario. `None` significa
    "sin informacion de permisos" y se trata como concedidos: es lo que necesitan los
    tests de servicio, y hace que un `None` descuidado no vuelva invisible el favorito
    de nadie.
    """
    if destino not in DESTINOS:
        return False
    if concedidos is None:
        return True
    return PERMISO_POR_DEFECTO in concedidos
