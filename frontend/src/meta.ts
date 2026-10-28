import { createContext, useContext } from 'react';
import type { Status } from './api';

export type Meta = {
  today: string;
  next_week: string;
  customers: { id: string; name: string }[];
  items: { sku: string; name: string }[];
  pos: string[];
};
export const MetaCtx = createContext<{ meta: Meta | null; status: Status | null; go: (v: string, id?: string | number) => void; refresh: () => void }>({
  meta: null, status: null, go: () => {}, refresh: () => {},
});
export const useApp = () => useContext(MetaCtx);
