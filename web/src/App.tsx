import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ResultsScreen } from "./features/results/ResultsScreen";
import { VotingScreen } from "./features/voting/VotingScreen";
import { useRouterStore } from "./lib/router";
import { SystemPage } from "./pages/SystemPage";

const queryClient = new QueryClient();

function Screen({ path }: { path: string }) {
  if (path === "/system") return <SystemPage />;
  if (path === "/results") return <ResultsScreen />;
  return <VotingScreen />;
}

export default function App() {
  const path = useRouterStore((state) => state.path);

  return (
    <QueryClientProvider client={queryClient}>
      <Screen path={path} />
    </QueryClientProvider>
  );
}
