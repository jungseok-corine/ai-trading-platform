import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { assignCandidate, getCandidates } from "../../api/research";

export default function CandidatesSection() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["candidates"], queryFn: () => getCandidates({ limit: 100 }) });

  const assignMut = useMutation({
    mutationFn: (id: number) => assignCandidate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assignment-logs"] }),
  });

  return (
    <div className="card">
      <h3>후보 종목 (Candidate Events)</h3>
      <p className="muted">스캐너 룰에 걸린 종목입니다. "왜 후보가 됐는지"가 facts/matched_conditions에 남습니다.</p>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {data && data.length === 0 && <p className="muted">후보가 없습니다. 스캐너에서 시장 스캔을 실행하세요.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr><th>ID</th><th>종목</th><th>점수</th><th>매칭 조건</th><th>facts</th><th>발견시각</th><th>배정</th></tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>{c.symbol_code}</td>
                  <td>{c.score}</td>
                  <td><code>{(c.matched_conditions ?? []).join(", ")}</code></td>
                  <td><pre className="parameters-cell">{JSON.stringify(c.facts, null, 1)}</pre></td>
                  <td>{new Date(c.triggered_at).toLocaleString()}</td>
                  <td>
                    <button disabled={assignMut.isPending} onClick={() => assignMut.mutate(c.id)}>
                      전략 배정
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {assignMut.isSuccess && (
        <p className="action-result value">
          {assignMut.data ? `전략 배정됨: ${assignMut.data.strategy_type}` : "매칭되는 배정 규칙이 없습니다."}
        </p>
      )}
    </div>
  );
}
