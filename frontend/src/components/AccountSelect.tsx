import { useQuery } from "@tanstack/react-query";
import { getAccounts } from "../api/client";
import type { Account } from "../types";

interface AccountSelectProps {
  id: string;
  value: number | null;
  onChange: (next: number | null) => void;
  /** true면 모의(PAPER) 계좌만 선택지로 노출(유니버스 자동매매는 모의 전용). */
  paperOnly?: boolean;
}

function accountLabel(a: Account): string {
  const type = a.account_type === "paper" ? "모의" : "실계좌";
  const name = a.alias ? `${a.alias} · ` : "";
  return `#${a.id} · ${type} · ${name}${a.broker_account_no}`;
}

export default function AccountSelect({ id, value, onChange, paperOnly }: AccountSelectProps) {
  const { data: accounts, isLoading, isError } = useQuery({
    queryKey: ["accounts"],
    queryFn: getAccounts,
  });

  const options = (accounts ?? []).filter((a) => !paperOnly || a.account_type === "paper");

  if (isError) {
    // 목록 조회 실패 시에도 직접 입력은 가능하도록 폴백(드물게).
    return (
      <input
        id={id}
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    );
  }

  return (
    <>
      <select
        id={id}
        value={value ?? ""}
        disabled={isLoading}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      >
        <option value="">— 계좌 선택 —</option>
        {options.map((a) => (
          <option key={a.id} value={a.id}>
            {accountLabel(a)}
          </option>
        ))}
      </select>
      {!isLoading && paperOnly && options.length === 0 && (
        <p className="section-description error">
          모의(PAPER) 계좌가 없습니다. 유니버스 자동매매는 모의계좌에서만 동작합니다.
        </p>
      )}
    </>
  );
}
