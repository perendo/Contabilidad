"""Servicios de documentos adjuntos al asiento (SPEC-030).

Cuatro modulos, uno por historia de usuario, para que US1, US2 y US3 puedan
avanzar sin editar el mismo fichero:

- ``errores``: ``DocumentoError`` con codigo estable y status HTTP.
- ``validacion``: firmas, ``pypdf`` y Pillow; logica de dominio sin sesion.
- ``adjuntos``: alta de uno o varios ficheros a un asiento (US1).
- ``consulta``: listado, metadatos y datos de descarga (US2).
- ``bajas``: baja logica con motivo, solo sobre asientos en borrador (US3).

Ningun modulo escribe en ``journal_entry`` ni en ``journal_entry_line``: es la
garantia estructural de FR-015 y SC-007.
"""

from __future__ import annotations
