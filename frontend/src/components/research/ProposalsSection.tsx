import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveProposal,
  generateProposal,
  getProposal,
  getProposals,
  rejectProposal,
  runStrategyReview,
} from "../../api/research";
import type { ProposalStatus } from "../../types/research";

const STATUS_FILTERS: (ProposalStatus | "all")[] = ["all", "pending", "approved", "rejected"];

function ProposalDetailPanel({ proposalId }: { proposalId: number }) {
  const { data } = useQuery({
    queryKey: ["proposal", proposalId],
    queryFn: () => getProposal(proposalId),
  });
  if (!data) return <p className="muted">불러오는 중...</p>;
  return (
    <div>
      {data.rationale && <p><strong>근거:</strong> {data.rationale}</p>}
      {data.expected_effect && <p><strong>예상 효과:</strong> {data.expected_effect}</p>}
      {data.risk_notes && <p><strong>리스크:</strong> {data.risk_notes}</p>}
      <p><strong>변경점 (before → after):</strong></p>
      {data.diff.length === 0 && <p className="muted">변경 없음</p>}
      {data.diff.length > 0 && (
        <table>
          <thead><tr><th>파라미터</th><th>before</th><th>after</th></tr></thead>
          <tbody>
            {data.diff.map((d) => (
              <tr key={d.key}>
                <td>{d.key}</td>
                <td>{JSON.stringify(d.before)}</td>
                <td><strong>{JSON.stringify(d.after)}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function ProposalsSection() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<ProposalStatus | "all">("all");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [genStrategyId, setGenStrategyId] = useState("");
  const [genVersionId, setGenVersionId] = useState("");
  const [genMsg, setGenMsg] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["proposals", filter],
    queryFn: () => getProposals(filter === "all" ? undefined : { status: filter }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["proposals"] });

  const approveMut = useMutation({
    mutationFn: (id: number) => approveProposal(id, { reviewed_by: "user" }),
    onSuccess: invalidate,
  });
  const rejectMut = useMutation({
    mutationFn: (id: number) => rejectProposal(id, { reviewed_by: "user" }),
    onSuccess: invalidate,
  });
  const generateMut = useMutation({
    mutationFn: () =>
      generateProposal({ strategy_id: Number(genStrategyId), version_id: Number(genVersionId) }),
    onSuccess: (p) => {
      setGenMsg(p ? `제안 생성됨 (#${p.id})` : "제안할 변경이 없습니다 (데이터 부족 또는 기대값 양수).");
      invalidate();
    },
    onError: (e) => setGenMsg((e as Error)?.message ?? "생성 실패"),
  });
  const reviewMut = useMutation({
    mutationFn: () => runStrategyReview(),
    onSuccess: (s) => {
      setGenMsg(
        `전체 점검 완료: ${s.versions_reviewed}개 버전 중 ${s.proposals_created}건 제안 생성, ${s.skipped_existing}건 건너뜀.`,
      );
      invalidate();
    },
    onError: (e) => setGenMsg((e as Error)?.message ?? "점검 실패"),
  });

  return (
    <div className="card">
      <h3>AI 전략 제안</h3>
      <p className="muted">
        AI가 전략 성과를 분석해 만든 개선 제안입니다. 승인 시에만 새 DRAFT 버전이 생성되며,
        자동매매는 켜지지 않습니다.
      </p>

      <div className="card" style={{ background: "#f8f9fa" }}>
        <strong>제안 자동 생성</strong>
        <div className="form-row">
          <input placeholder="strategy_id" value={genStrategyId}
            onChange={(e) => setGenStrategyId(e.target.value)} />
          <input placeholder="version_id" value={genVersionId}
            onChange={(e) => setGenVersionId(e.target.value)} />
          <button className="primary" disabled={!genStrategyId || !genVersionId || generateMut.isPending}
            onClick={() => generateMut.mutate()}>
            성과 분석 → 제안 생성
          </button>
          <button disabled={reviewMut.isPending} onClick={() => reviewMut.mutate()}>
            전체 전략 자동 점검
          </button>
        </div>
        {genMsg && <p className="action-result value">{genMsg}</p>}
      </div>

      <div className="form-row">
        {STATUS_FILTERS.map((s) => (
          <button key={s} className={filter === s ? "primary" : undefined} onClick={() => setFilter(s)}>
            {s}
          </button>
        ))}
      </div>

      {isLoading && <p className="muted">불러오는 중...</p>}
      {data && data.length === 0 && <p className="muted">제안이 없습니다.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr><th>ID</th><th>제목</th><th>전략</th><th>상태</th><th>출처</th><th>상세</th><th>검토</th></tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{p.title}</td>
                  <td>#{p.strategy_id}</td>
                  <td><span className={`badge badge-${p.status}`}>{p.status}</span></td>
                  <td>{p.source}</td>
                  <td>
                    <button onClick={() => setExpanded(expanded === p.id ? null : p.id)}>
                      {expanded === p.id ? "닫기" : "보기"}
                    </button>
                  </td>
                  <td>
                    {p.status === "pending" ? (
                      <>
                        <button className="primary" disabled={approveMut.isPending}
                          onClick={() => approveMut.mutate(p.id)}>승인</button>
                        <button className="danger" disabled={rejectMut.isPending}
                          onClick={() => rejectMut.mutate(p.id)}>거절</button>
                      </>
                    ) : (
                      <span className="muted">{p.reviewed_by ?? "-"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {expanded !== null && (
        <div className="card"><ProposalDetailPanel proposalId={expanded} /></div>
      )}
    </div>
  );
}
