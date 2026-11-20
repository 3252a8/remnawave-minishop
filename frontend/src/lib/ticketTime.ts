const options: Intl.DateTimeFormatOptions = {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
};

export function formatTicketTime(value: string | null | undefined, locale: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  try {
    return date.toLocaleString(locale, options);
  } catch {
    // Administrators can name custom translation packs independently of BCP 47.
    return date.toLocaleString(undefined, options);
  }
}
