interface AutoTradeToggleProps {
  value: boolean;
  accountId: number | null;
  quantity: number;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}

const CONFIRM_TEXT =
  "자동 주문이 활성화됩니다. KIS VTS 모의투자 계좌로 실제 모의 주문이 전송될 수 있습니다. 계속하시겠습니까?";

export default function AutoTradeToggle({
  value,
  accountId,
  quantity,
  onChange,
  disabled,
}: AutoTradeToggleProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.checked;

    if (!next) {
      onChange(false);
      return;
    }

    if (accountId === null || accountId === undefined) {
      window.alert("account_id가 설정되지 않았습니다. auto_trade_enabled를 활성화하려면 account_id를 입력하세요.");
      return;
    }

    if (!window.confirm(CONFIRM_TEXT)) {
      return;
    }

    if (quantity > 1) {
      if (!window.confirm(`주문 수량이 ${quantity}로 설정되어 있습니다. 이대로 자동 주문을 활성화하시겠습니까?`)) {
        return;
      }
    }

    onChange(true);
  };

  return (
    <label className="auto-trade-toggle">
      <input type="checkbox" checked={value} onChange={handleChange} disabled={disabled} />
      <span>auto_trade_enabled</span>
      {value && <span className="pill on">ON</span>}
      {!value && <span className="pill off">OFF</span>}
    </label>
  );
}
