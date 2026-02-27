import { useSearch, useNavigate } from "@tanstack/react-router";

export function useConnection() {
  const search = useSearch({ strict: false }) as { connection?: string };
  const navigate = useNavigate();

  const connection = search.connection ?? "";

  const setConnection = (conn: string) => {
    void navigate({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      search: { connection: conn || undefined } as any,
    });
  };

  return { connection, setConnection };
}
