import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveProposal,
  bulkReviewStrategyProposals,
  generateProposal,
  getProposals,
  rejectProposal,
  runStrategyReview,
} from "../../api/research";
import type { ProposalStatus } from "../../types/research";
import StrategyProposalReportCard from "./StrategyProposalReportCard";

const STATUS_FILTERS: (ProposalStatus | "all")[] = ["all", "pending", "approved", "rejected"];

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
  const pendingIds = (data ?? []).filter((p) => p.status === "pending").map((p) => p.id);
  const bulkMut = useMutation({
    mutationFn: (action: "approve" | "reject") => bulkReviewStrategyProposals(pendingIds, action),
    onSuccess: (r) => {
      setGenMsg(`일괄 ${r.action}: 성공 ${r.succeeded.length}건, 실패 ${r.failed.length}건.`);
      invalidate();
    },
    onError: (e) => setGenMsg((e as Error)?.message ?? "일괄 처리 실패"),
  });

  return (
    <div className="card">
      <h3>AI 전략 제안</h3>
      <p className="muted">
        AI가 전략 성과를 분석해 만든 개선 제안입니다. 승인 시에만 새 TESTING 버전이 생성되며,
        자동매매는 켜지지 않습니다. 승인 전 「검토 리포트」에서 변경점과 안전 사항을 확인하세요.
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
        {pendingIds.length > 0 && (
          <>
            <button className="primary" disabled={bulkMut.isPending}
              onClick={() => bulkMut.mutate("approve")}>
              보이는 pending {pendingIds.length}건 일괄 승인
            </button>
            <button className="danger" disabled={bulkMut.isPending}
              onClick={() => bulkMut.mutate("reject")}>
              일괄 거절
            </button>
          </>
        )}
      </div>

      {isLoading && <p className="muted">불러오는 중...</p>}
      {data && data.length === 0 && <p className="muted">제안이 없습니다.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr><th>ID</th><th>제목</th><th>전략</th><th>상태</th><th>출처</th><th>검토 리포트</th></tr>
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
                      {expanded === p.id ? "닫기" : "검토 리포트"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {expanded !== null && (
        <StrategyProposalReportCard
          key={expanded}
          proposalId={expanded}
          status={(data ?? []).find((p) => p.id === expanded)?.status ?? "pending"}
          approving={approveMut.isPending}
          rejecting={rejectMut.isPending}
          onApprove={() => approveMut.mutate(expanded)}
          onReject={() => rejectMut.mutate(expanded)}
        />
      )}
    </div>
  );
}
