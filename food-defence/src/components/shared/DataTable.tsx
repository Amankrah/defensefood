"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { fmt } from "@/lib/utils";

export interface Column<T> {
  key: string;
  label: string;
  /** Shown on header hover: what the number means for decisions */
  headerDescription?: string;
  type?: "string" | "number";
  render?: (row: T) => React.ReactNode;
  sortable?: boolean;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (row: T) => void;
  pageSize?: number;
  searchKeys?: string[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function DataTable<T extends Record<string, any>>({
  columns,
  data,
  onRowClick,
  pageSize = 25,
  searchKeys = [],
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string>("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (!search.trim()) return data;
    const q = search.toLowerCase();
    return data.filter((row) =>
      searchKeys.some((k) =>
        String(row[k] ?? "")
          .toLowerCase()
          .includes(q)
      )
    );
  }, [data, search, searchKeys]);

  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    const col = columns.find((c) => c.key === sortKey);
    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (col?.type === "number") {
        const an =
          typeof av === "number" && !Number.isNaN(av) ? av : null;
        const bn =
          typeof bv === "number" && !Number.isNaN(bv) ? bv : null;
        if (an === null && bn === null) return 0;
        if (an === null) return 1;
        if (bn === null) return -1;
        return (an - bn) * dir;
      }
      return String(av ?? "").localeCompare(String(bv ?? "")) * dir;
    });
  }, [filtered, sortKey, sortDir, columns]);

  const paged = sorted.slice(page * pageSize, (page + 1) * pageSize);
  const totalPages = Math.ceil(sorted.length / pageSize);

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
    setPage(0);
  }

  return (
    <div>
      {searchKeys.length > 0 && (
        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          className="mb-3 w-full max-w-xs px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              {columns.map((col) => (
                <th
                  key={col.key}
                  title={col.headerDescription}
                  className={`pb-2.5 pr-3 font-medium text-gray-500 text-xs ${
                    col.type === "number" ? "text-right" : ""
                  } ${col.sortable !== false ? "cursor-pointer select-none hover:text-gray-700" : ""} ${col.className ?? ""}`}
                  onClick={() => col.sortable !== false && toggleSort(col.key)}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    {sortKey === col.key &&
                      (sortDir === "asc" ? (
                        <ChevronUp size={12} />
                      ) : (
                        <ChevronDown size={12} />
                      ))}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((row, i) => (
              <tr
                key={i}
                className={`border-b border-gray-100 ${
                  onRowClick
                    ? "cursor-pointer hover:bg-blue-50/50"
                    : "hover:bg-gray-50"
                }`}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`py-2 pr-3 ${
                      col.type === "number"
                        ? "text-right font-mono text-gray-700"
                        : "text-gray-800"
                    } ${col.className ?? ""}`}
                  >
                    {col.render
                      ? col.render(row)
                      : col.type === "number"
                      ? fmt(row[col.key] as number)
                      : String(row[col.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
          <span>
            {sorted.length} results, page {page + 1} of {totalPages}
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-2 py-1 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
            >
              Prev
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
