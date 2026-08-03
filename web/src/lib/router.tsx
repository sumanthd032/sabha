import type { AnchorHTMLAttributes, MouseEvent } from "react";
import { create } from "zustand";

/**
 * A path-only router. There is no nested or parameterised routing need
 * yet, and react-router is not on the approved dependency list, so this
 * is a store holding the current pathname plus a Link that intercepts
 * plain clicks, in the spirit of writing the small things by hand.
 */

interface RouterState {
  path: string;
  navigate: (path: string) => void;
}

function currentPath(): string {
  return window.location.pathname;
}

export const useRouterStore = create<RouterState>((set) => ({
  path: currentPath(),
  navigate: (path: string) => {
    window.history.pushState({}, "", path);
    set({ path });
  },
}));

window.addEventListener("popstate", () => {
  useRouterStore.setState({ path: currentPath() });
});

interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  to: string;
}

export function Link({ to, onClick, ...rest }: LinkProps) {
  const navigate = useRouterStore((state) => state.navigate);
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (event.defaultPrevented) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    navigate(to);
  };
  return <a href={to} onClick={handleClick} {...rest} />;
}
