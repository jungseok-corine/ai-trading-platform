import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveScannerProposal,
  bulkReviewScannerProposals,
  generateScannerProposal,
  getScannerProposal,
  getScannerProposals,
  rejectScannerProposal,
  runScannerReview,
} from "../../api/research";
import type { ProposalStatus } from "../../types/research";

const STATUS_FILTERS: (ProposalStatus | "all")[] = ["all", "pending", "approved", "rejected"];

function ProposalDetailPanel({ proposalId }: { proposalId: number }) {
  const { data } = useQuery({
    queryKey: ["scanner-proposal", proposalId],
    queryFn: () => getScannerProposal(proposalId),
  });
  if (!data) return <p className="muted">불러오는 중...</p>;
  return (
    <div>
      {data.rationale && <p><strong>근거:</strong> {data.rationale}</p>}
      {data.expected_effect && <p><strong>예상 효과:</strong> {data.expected_effect}</p>}
      {data.risk_notes && <p><strong>리스크:</strong> {data.risk_notes}</p>}
      <p><strong>조건 변경 (before → after):</strong></p>
      {data.diff.length === 0 && <p className="muted">변경 없음</p>}
      {data.diff.length > 0 && (
        <table>
          <thead><tr><th>조건 타입</th><th>before</th><th>after</th></tr></thead>
          <tbody>
            {data.diff.map((d) => (
              <tr key={d.type}>
                <td>{d.type}</td>
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

export default function ScannerProposalsSection() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<ProposalStatus | "all">("all");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [genVersionId, setGenVersionId] = useState("");
  const [genMsg, setGenMsg] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["scanner-proposals", filter],
    queryFn: () => getScannerProposals(filter === "all" ? undefined : { status: filter }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["scanner-proposals"] });

  const approveMut = useMutation({
    mutationFn: (id: number) => approveScannerProposal(id, { reviewed_by: "user" }),
    onSuccess: invalidate,
  });
  const rejectMut = useMutation({
    mutationFn: (id: number) => rejectScannerProposal(id, { reviewed_by: "user" }),
    onSuccess: invalidate,
  });
  const generateMut = useMutation({
    mutationFn: () => generateScannerProposal({ version_id: Number(genVersionId) }),
    onSuccess: (p) => {
      setGenMsg(p ? `제안 생성됨 (#${p.id})` : "제안할 변경이 없습니다 (데이터 부족 또는 승률이 기준 이상).");
      invalidate();
    },
    onError: (e) => setGenMsg((e as Error)?.message ?? "생성 실패"),
  });
  const reviewMut = useMutation({
    mutationFn: () => runScannerReview(),
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
    mutationFn: (action: "approve" | "reject") => bulkReviewScannerProposals(pendingIds, action),
    onSuccess: (r) => {
      setGenMsg(`일괄 ${r.action}: 성공 ${r.succeeded.length}건, 실패 ${r.failed.length}건.`);
      invalidate();
    },
    onError: (e) => setGenMsg((e as Error)?.message ?? "일괄 처리 실패"),
  });

  return (
    <div className="card">
      <h3>AI 스캐너 제안</h3>
      <p className="muted">
        AI가 후보 성과 분석을 근거로 만든 스캐너 '조건 강화' 제안입니다. 승률이 낮은 룰의 진입
        문턱을 높입니다. 승인 시에만 새 DRAFT 룰 버전이 생성되며, 룰은 자동 활성화되지 않습니다.
      </p>

      <div className="card" style={{ background: "#f8f9fa" }}>
        <strong>제안 자동 생성</strong>
        <div className="form-row">
          <input placeholder="scanner_rule_version_id" value={genVersionId}
            onChange={(e) => setGenVersionId(e.target.value)} />
          <button className="primary" disabled={!genVersionId || generateMut.isPending}
            onClick={() => generateMut.mutate()}>
            후보 성과 분석 → 제안 생성
          </button>
          <button disabled={reviewMut.isPending} onClick={() => reviewMut.mutate()}>
            전체 룰 자동 점검
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
              <tr><th>ID</th><th>제목</th><th>룰</th><th>상태</th><th>출처</th><th>상세</th><th>검토</th></tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{p.title}</td>
                  <td>#{p.scanner_rule_id}</td>
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
