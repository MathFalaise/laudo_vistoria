import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes, useParams } from "react-router-dom";

import { Erro } from "../App";
import { api, type Comodo, type Job, type Vistoria } from "../api";
import { PainelFotos } from "./Fotos";
import { PainelLaudo } from "./Laudo";
import { PainelPendencias } from "./Pendencias";

export function TelaVistoria() {
  const { id = "" } = useParams();
  const [vistoria, setVistoria] = useState<Vistoria | null>(null);
  const [erro, setErro] = useState<unknown>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [usarEvidencias, setUsarEvidencias] = useState(true);

  const recarregar = useCallback(async () => {
    try {
      setVistoria(await api.vistoria(id));
    } catch (falha) {
      setErro(falha);
    }
  }, [id]);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  // Enquanto houver job em andamento, acompanha o progresso. O intervalo para
  // sozinho quando o job termina — nada de sondar para sempre.
  useEffect(() => {
    if (!job || job.estado === "completed" || job.estado === "failed" || job.estado === "cancelled") {
      return;
    }
    const temporizador = setInterval(async () => {
      try {
        const atual = await api.job(job.id);
        setJob(atual);
        if (atual.estado !== "processing" && atual.estado !== "pending") {
          clearInterval(temporizador);
          await recarregar();
        }
      } catch {
        clearInterval(temporizador);
      }
    }, 1500);
    return () => clearInterval(temporizador);
  }, [job, recarregar]);

  async function processar(reprocessar = false) {
    setErro(null);
    try {
      setJob(await api.processar(id, { usar_evidencias: usarEvidencias, reprocessar_concluidos: reprocessar }));
    } catch (falha) {
      setErro(falha);
    }
  }

  if (!vistoria) {
    return (
      <main className="conteudo">
        <Erro erro={erro} />
        {!erro && <div className="vazio">Carregando…</div>}
      </main>
    );
  }

  const comodos = vistoria.lista_comodos ?? [];
  const emAndamento = job?.estado === "processing" || job?.estado === "pending";

  return (
    <>
      <nav className="abas">
        <NavLink end to={`/vistorias/${id}`} className={({ isActive }) => (isActive ? "ativa" : "")}>
          Fotos
        </NavLink>
        <NavLink to={`/vistorias/${id}/laudo`} className={({ isActive }) => (isActive ? "ativa" : "")}>
          Laudo
        </NavLink>
        <NavLink to={`/vistorias/${id}/pendencias`} className={({ isActive }) => (isActive ? "ativa" : "")}>
          Pendências
          {vistoria.pendencias.abertas > 0 && (
            <span className={vistoria.pendencias.por_tipo.scope_conflict ? "etiqueta perigo" : "etiqueta alerta"}>
              {vistoria.pendencias.abertas}
            </span>
          )}
        </NavLink>
      </nav>

      <main className="conteudo">
        <div className="entre" style={{ marginBottom: 12 }}>
          <div>
            <h1 style={{ fontSize: 20, margin: 0 }}>{vistoria.titulo}</h1>
            <p className="fraco" style={{ margin: 0 }}>
              {vistoria.comodos} cômodo(s) · {vistoria.fotos} foto(s)
            </p>
          </div>
          <div className="linha">
            <a className="botao pequeno" href={api.urlLaudoTxt(id)}>Laudo .txt</a>
            <a className="botao pequeno" href={api.urlZip(id)}>ZIP</a>
          </div>
        </div>

        <Erro erro={erro} />

        <ControleProcessamento
          job={job}
          emAndamento={!!emAndamento}
          usarEvidencias={usarEvidencias}
          aoTrocarMotor={setUsarEvidencias}
          aoProcessar={processar}
          temFotos={comodos.some((c) => c.fotos > 0)}
        />

        <Routes>
          <Route
            index
            element={<PainelFotos vistoriaId={id} comodos={comodos} aoMudar={recarregar} />}
          />
          <Route path="laudo" element={<PainelLaudo vistoriaId={id} />} />
          <Route
            path="pendencias"
            element={<PainelPendencias vistoriaId={id} aoDecidir={recarregar} />}
          />
        </Routes>
      </main>
    </>
  );
}

function ControleProcessamento({
  job,
  emAndamento,
  usarEvidencias,
  aoTrocarMotor,
  aoProcessar,
  temFotos,
}: {
  job: Job | null;
  emAndamento: boolean;
  usarEvidencias: boolean;
  aoTrocarMotor: (valor: boolean) => void;
  aoProcessar: (reprocessar?: boolean) => void;
  temFotos: boolean;
}) {
  const percentual = job && job.total > 0 ? Math.round((job.concluidos / job.total) * 100) : 0;

  return (
    <div className="cartao">
      <div className="entre">
        <div>
          <h3 style={{ margin: 0 }}>Processamento</h3>
          <label className="linha fraco" style={{ margin: "6px 0 0", fontWeight: 400, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={usarEvidencias}
              onChange={(e) => aoTrocarMotor(e.target.checked)}
              style={{ width: 18, height: 18, margin: 0 }}
              disabled={emAndamento}
            />
            Validar escopo de cada foto antes de escrever
          </label>
        </div>
        <div className="linha">
          <button className="principal" onClick={() => aoProcessar(false)} disabled={emAndamento || !temFotos}>
            {emAndamento ? "Processando…" : "Processar"}
          </button>
          <button onClick={() => aoProcessar(true)} disabled={emAndamento || !temFotos}>
            Refazer tudo
          </button>
        </div>
      </div>

      {usarEvidencias && (
        <p className="fraco" style={{ marginTop: 8, marginBottom: 0 }}>
          Cada foto é classificada antes (é deste cômodo? é reflexo? mostra ambiente
          vizinho?) e só o que passa vira texto. O que for descartado vira pendência,
          não some.
        </p>
      )}

      {job && (
        <div style={{ marginTop: 12 }}>
          <div className="entre" style={{ marginBottom: 6 }}>
            <span className="fraco">{job.mensagem || job.estado}</span>
            <span className="fraco">
              {job.concluidos}/{job.total}
            </span>
          </div>
          <div className="barra-progresso">
            <div style={{ width: `${percentual}%` }} />
          </div>
          {job.erro && <div className="aviso" style={{ marginTop: 10 }}>{job.erro}</div>}
        </div>
      )}

      {!temFotos && (
        <p className="fraco" style={{ marginTop: 10, marginBottom: 0 }}>
          Crie um cômodo e envie as fotos para poder processar.
        </p>
      )}
    </div>
  );
}

/** Marcador de estado do cômodo, reaproveitado nas telas. */
export function EstadoComodo({ comodo }: { comodo: Comodo }) {
  if (comodo.estado === "concluido") {
    return <span className="etiqueta ok">pronto</span>;
  }
  if (comodo.estado === "processando") {
    return <span className="etiqueta info">processando</span>;
  }
  if (comodo.estado === "falhou") {
    return <span className="etiqueta perigo">falhou</span>;
  }
  return <span className="etiqueta neutra">a processar</span>;
}

/** Hook simples de recarregamento, usado pelos painéis. */
export function useCarregar<T>(carregar: () => Promise<T>, dependencias: unknown[]) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<unknown>(null);
  const montado = useRef(true);

  const recarregar = useCallback(async () => {
    try {
      const resultado = await carregar();
      if (montado.current) setDados(resultado);
    } catch (falha) {
      if (montado.current) setErro(falha);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencias);

  useEffect(() => {
    montado.current = true;
    void recarregar();
    return () => {
      montado.current = false;
    };
  }, [recarregar]);

  return { dados, erro, recarregar };
}
