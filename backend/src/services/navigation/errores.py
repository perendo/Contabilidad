"""VARIOS DE NAVEGACION (SPEC-031, research D9).

Los codigos de error son parte del contrato publico: el frontend los usa para
mensajes y `api-contracts.md` los documenta uno a uno. Anadirlos aqui y no en
cada servicio evita que dos servicios inventen el mismo codigo con distinto
significado.
"""

from __future__ import annotations


class NavigationError(Exception):
    """Error de la capa de navegacion, con codigo y codigo HTTP.

    El patron es el de `services/budget/errores.py` y `services/export/errores.py`:
    el servicio lanza y la capa de API traduce.
    """

    def __init__(self, code: str, detail: str, status_code: int = 422) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


def error(code: str, detail: str, status_code: int = 422) -> NavigationError:
    """Construye el error. Evita repetir los tres parametros en cada sitio."""
    return NavigationError(code=code, detail=detail, status_code=status_code)


#: El ejercicio de la cabecera no pertenece a la empresa de la sesion.
#: Se espera 422 y no 404: el ejercicio existe, simplemente no es de esta empresa,
#: y decirlo revelaria informacion de otro tenant (constitution III).
EJERCICIO_NO_PERTENECE_A_EMPRESA = "ejercicio_no_pertenece_a_empresa"

#: La clave de destino no existe en el mapa de superficies. 404: es un recurso
#: ausente del catalogo, no un valor invalido.
DESTINO_DESCONOCIDO = "destino_desconocido"

#: `orden` con valor fuera de rango. 422.
#: OJO: este codigo concierne al VALOR de la posicion, no a la cantidad de
#: favoritos. Superar el maximo de 5 NO es un error: se guarda y se recorta en la
#: lectura (research D5, caso borde CHK025).
ORDEN_FUERA_DE_RANGO = "orden_fuera_de_rango"

#: El reordenado no contiene exactamente el conjunto actual. 422.
CONJUNTO_INCOMPLETO = "conjunto_incompleto"
