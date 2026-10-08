"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Error capturado por error boundary:", error);
  }, [error]);

  return (
    <div className="min-h-[50vh] flex flex-col items-center justify-center p-6 text-center">
      <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 max-w-lg w-full space-y-4 shadow-sm">
        <div className="w-10 h-10 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center mx-auto font-bold text-lg">
          !
        </div>
        <h2 className="text-base font-bold text-slate-900">Se produjo un error al cargar la vista</h2>
        <p className="text-xs text-slate-600 font-mono bg-white p-3 rounded-lg border border-slate-200 break-words text-left">
          {error.message || "Error desconocido"}
        </p>
        <button
          onClick={() => reset()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition-colors shadow-sm"
        >
          Reintentar
        </button>
      </div>
    </div>
  );
}
