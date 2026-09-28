# Specification Quality Checklist: Documentos adjuntos al asiento (diario contable)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-26
**Feature**: [specs/030-documentos-asiento/spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Segunda iteración: los 16 ítems pasan. Los 3 marcadores `[NEEDS CLARIFICATION]` de la
  primera pasada (FR-001, FR-010 y FR-012) se resolvieron con las decisiones del usuario
  (A, A, A) y se redactaron como requisitos cerrados.
- Decisiones incorporadas:
  - Alcance: el anclaje es exclusivamente el asiento del diario; facturas, vencimientos,
    extractos y modelos fiscales se rechazan en esta versión (FR-001).
  - Estados: adjuntar se permite en borrador y en asiento contabilizado; dar de baja solo en
    borrador, y se rechaza sobre un asiento ya contabilizado (FR-010, SC-011, caso límite
    "Baja solicitada sobre un asiento ya contabilizado").
  - Baja: siempre lógica, con motivo, responsable y fecha; el contenido y la huella se
    conservan durante el plazo legal y los datos personales se atenúan por permisos, sin
    suprimir el soporte (FR-012, escenario US3.4).
- Constitución: FR-013 (aislamiento), FR-015 (partida doble intacta), FR-009/FR-011
  (inmutabilidad del contenido y auditoría) y FR-016 (permisos) cubren los principios I, II,
  III y V. La prohibición de coma flotante solo aplica al importe informativo opcional
  (ver Supuestos).
- Alcance declarado fuera de la funcionalidad: OCR, firma digital, carpetas o ZIP,
  clasificación automática, gestores documentales externos y la incorporación de los
  documentos al libro-diario PDF oficial y a la exportación integral (SPEC-019 y SPEC-029).
- Cifrado verificado: el fichero UTF-8 no contiene caracteres fuera del alfabeto español
  ni sustituciones corruptas.
