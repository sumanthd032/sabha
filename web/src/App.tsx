import { useRouterStore } from "./lib/router";
import { SystemPage } from "./pages/SystemPage";

export default function App() {
  const path = useRouterStore((state) => state.path);

  if (path === "/system") {
    return <SystemPage />;
  }

  return null;
}
