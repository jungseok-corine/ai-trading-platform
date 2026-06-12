import { useSettings, type Timezone } from "./SettingsContext";
import type { Language } from "./translations";

export default function SettingsBar() {
  const { language, setLanguage, timezone, setTimezone, t } = useSettings();

  return (
    <div className="settings-bar">
      <label>
        {t.settings.language}
        <select value={language} onChange={(e) => setLanguage(e.target.value as Language)}>
          <option value="ko">{t.settings.languageKo}</option>
          <option value="en">{t.settings.languageEn}</option>
        </select>
      </label>
      <label>
        {t.settings.timezone}
        <select value={timezone} onChange={(e) => setTimezone(e.target.value as Timezone)}>
          <option value="Asia/Seoul">{t.settings.timezoneSeoul}</option>
          <option value="Asia/Bangkok">{t.settings.timezoneBangkok}</option>
          <option value="UTC">{t.settings.timezoneUtc}</option>
        </select>
      </label>
    </div>
  );
}
