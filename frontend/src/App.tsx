import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { ErroApi, api, type Usuario } from "./api";
import { Login } from "./telas/Login";
import { ListaVistorias } from "./telas/Vistorias";
import { TelaVistoria } from "./telas/Vistoria";
import { TelaRegras } from "./telas/Regras";

export function App() {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [carregando, setCarregando] = useState(true);
  const navegar = useNavigate();

  useEffect(() => {
    // Uma sessão válida já no cookie evita pedir login de novo a cada aba.
    api
      .eu()
      .then(setUsuario)
      .catch((erro) => {
        if (!(erro instanceof ErroApi && erro.status === 401)) console.error(erro);
      })
      .finally(() => setCarregando(false));
  }, []);

  const sair = useCallback(async () => {
    await api.sair().catch(() => undefined);
    setUsuario(null);
    navegar("/");
  }, [navegar]);

  if (carregando) {
    return <div className="vazio">Carregando…</div>;
  }

  if (!usuario) {
    return <Login aoEntrar={setUsuario} />;
  }

  return (
    <>
      <header className="cabecalho">
        <Link to="/" className="titulo">
          Laudo de Vistoria
          <span>{usuario.email}</span>
        </Link>
        <Link to="/regras" className="botao pequeno">
          Regras
        </Link>
        <button className="pequeno" onClick={sair}>
          Sair
        </button>
      </header>
      <Routes>
        <Route path="/" element={<ListaVistorias />} />
        <Route path="/vistorias/:id/*" element={<TelaVistoria />} />
        <Route path="/regras" element={<TelaRegras />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

/** Mensagem de erro padronizada. Uma sessão expirada volta ao login em vez de
 *  deixar a tela em branco. */
export function Erro({ erro }: { erro: unknown }) {
  if (!erro) return null;
  const mensagem =
    erro instanceof ErroApi
      ? erro.status === 401
        ? "Sua sessão expirou. Recarregue a página para entrar de novo."
        : erro.message
      : "Não foi possível falar com o servidor.";
  return <div className="erro">{mensagem}</div>;
}
