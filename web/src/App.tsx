import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { VotingScreen } from "./features/voting/VotingScreen";
import { useRouterStore } from "./lib/router";
import { SystemPage } from "./pages/SystemPage";

const queryClient = new QueryClient();

export default function App() {
  const path = useRouterStore((state) => state.path);

  return (
    <QueryClientProvider client={queryClient}>
      {path === "/system" ? <SystemPage /> : <VotingScreen />}
    </QueryClientProvider>
  );
}
