import { get, post, request } from "../../services/client";

export type TemplateVariable = {
  id: string;
  nombre: string;
  tipo: string;
  es_requerida: boolean;
};

export type TemplateLine = {
  id: string;
  orden: number;
  cuenta_id: number;
  posicion: "debe" | "haber";
  importe_fijo: string | null;
  variable_id: string | null;
};

export type AccountingTemplate = {
  id: string;
  nombre: string;
  descripcion: string | null;
  categoria: string | null;
  version_actual: number;
  estado: "activa" | "inactiva";
  variables: TemplateVariable[];
  lineas: TemplateLine[];
};

export type TemplateInput = {
  nombre: string;
  descripcion?: string;
  categoria?: string;
  variables: Array<{ id?: string; nombre: string; es_requerida: boolean }>;
  lineas: Array<{
    orden: number;
    cuenta_id: number;
    posicion: "debe" | "haber";
    importe_fijo?: string;
    variable_id?: string;
  }>;
};

export function listarPlantillas(): Promise<{ items: AccountingTemplate[]; total: number }> {
  return get("/api/v1/plantillas");
}

export function obtenerPlantilla(id: string): Promise<AccountingTemplate> {
  return get(`/api/v1/plantillas/${id}`);
}

export function crearPlantilla(body: TemplateInput): Promise<AccountingTemplate> {
  return post("/api/v1/plantillas", body);
}

export function editarPlantilla(id: string, body: Partial<TemplateInput>): Promise<AccountingTemplate> {
  return request(`/api/v1/plantillas/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export function cambiarEstadoPlantilla(id: string, estado: "activar" | "inactivar"): Promise<{ id: string; estado: string }> {
  return post(`/api/v1/plantillas/${id}/${estado}`);
}

export function generarDesdePlantilla(id: string, body: { fecha_asiento: string; variables: Record<string, string>; concepto?: string }): Promise<unknown> {
  return post(`/api/v1/plantillas/${id}/generar`, body);
}

export function listarGenerados(id: string): Promise<{ items: Array<Record<string, unknown>>; total: number }> {
  return get(`/api/v1/plantillas/${id}/generados`);
}
