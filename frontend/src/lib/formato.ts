/**
 * Utilidades de formateo para números y moneda española.
 * Formato estándar español: separador de miles con punto (.) y decimal con coma (,)
 * Ejemplo: 1250.65 -> "1.250,65" o "1.250,65 €"
 */

export function formatearMoneda(
  valor: number | string | null | undefined,
  incluirSimbolo = false
): string {
  if (valor === null || valor === undefined || valor === "") {
    return "0,00" + (incluirSimbolo ? " €" : "");
  }

  const num = typeof valor === "number" ? valor : parseFloat(String(valor).replace(/,/g, "."));
  if (isNaN(num)) {
    return String(valor);
  }

  const partes = num.toFixed(2).split(".");
  const enteroFormateado = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decimales = partes[1] || "00";

  const formateado = `${enteroFormateado},${decimales}`;
  return incluirSimbolo ? `${formateado} €` : formateado;
}

export function formatearDecimal4(
  valor: number | string | null | undefined,
  incluirSimbolo = false
): string {
  if (valor === null || valor === undefined || valor === "") {
    return "0,0000" + (incluirSimbolo ? " €" : "");
  }

  const num = typeof valor === "number" ? valor : parseFloat(String(valor).replace(/,/g, "."));
  if (isNaN(num)) {
    return String(valor);
  }

  const partes = num.toFixed(4).split(".");
  const enteroFormateado = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decimales = partes[1] || "0000";

  const formateado = `${enteroFormateado},${decimales}`;
  return incluirSimbolo ? `${formateado} €` : formateado;
}
