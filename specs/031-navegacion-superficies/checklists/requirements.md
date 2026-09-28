# Specification Quality Checklist: Navegación y superficies

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-27
**Feature**: [spec.md](../spec.md)

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

**Validación en dos pasadas.**

- **Iteración 1, reprobada.** Al escribir el fichero se introdujeron 7
  corrupciones de caracteres no latinos (CJK, árabe y hangul) que dejaban
  fragmentos de frase ilegibles dentro de requisitos, 4 mezclas de idioma o
  palabras partidas dentro de requisitos, y 2 anglicismos sin traducir.
  Todo corregido.
- **Iteración 2, aprobada.** Sin marcadores pendientes: 29 requisitos
  funcionales, 12 criterios de éxito, 6 historias de usuario y 10 casos límite.

**Lección sobre el control de calidad:** la comprobación válida es un barrido
del fichero entero contra el juego de caracteres permitido (ASCII más tildes y
signos españoles), no solo contra el rango CJK. Un rango CJK deja pasar el
árabe y el hangul, que es precisamente lo que se coló.

**Sobre las ambigüedades deliberadas:**

- **FR-006** («el permiso mínimo que ya posea cualquier usuario con acceso a la
  contabilidad») está redactado en términos de propiedad del permiso, no de
  nombre de permiso, para no fijar en el spec un detalle de la matriz de
  permisos. `/speckit.plan` lo traduce al permiso concreto.
- **FR-011** («sin exceder el número de destinos que admite una barra
  inferior») delega el número al plan, donde se fija con la regla de diseño
  correspondiente.
- **FR-015** fija el criterio (no usar siglas como única denominación) sin
  enumerar qué siglas se aceptan: esa lista depende de qué exista hoy en el
  programa y se resuelve en el plan.

**Límite de alcance asumido.** El spec excluye expresamente la gestión de
usuarios, el cambio obligatorio de contraseña y el registro de quién realiza cada
apunte, que el usuario ha decidido Trasladar a una feature posterior de
seguridad. El requisito FR-001 se limita a impedir el acceso sin sesión
identificada, que es la necesidad de navegación, y no amplía el modelo de
permisos.
