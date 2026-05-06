import { AlertTriangle, Building2, Search, Ship, User, X } from "lucide-react";
import debounce from "lodash.debounce";
import { useEffect, useMemo, useState, type ReactNode } from "react";

type EntityType = "person" | "organization" | "vessel";

type SearchEntity = {
  id: string;
  name: string;
  type: EntityType;
  countries: string[];
  programs: string[];
  remarks: string | null;
  search_score: number;
  match_type: string;
  collision_warning: string | null;
  is_recent: boolean;
};

const API_URL = "http://localhost:8000/api/search";

function formatMatchType(matchType: string): string {
  return matchType
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getEntityIcon(type: EntityType) {
  if (type === "person") {
    return User;
  }
  if (type === "vessel") {
    return Ship;
  }
  return Building2;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function highlightText(text: string, query: string): ReactNode {
  const terms = query
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((term) => escapeRegex(term));

  if (!terms.length) {
    return text;
  }

  const pattern = new RegExp(`\\b(${terms.join("|")})\\b`, "ig");
  const parts = text.split(pattern);
  const normalizedTerms = terms.map((term) => term.toLowerCase());

  return parts.map((part, index) =>
    normalizedTerms.includes(part.toLowerCase()) ? (
      <mark key={`${part}-${index}`} className="rounded bg-cyan-400/20 px-0.5 text-cyan-200">
        {part}
      </mark>
    ) : (
      <span key={`${part}-${index}`}>{part}</span>
    )
  );
}

export default function App() {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [results, setResults] = useState<SearchEntity[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(-1);

  const debouncedSetSearch = useMemo(
    () => debounce((value: string) => setDebouncedQuery(value), 300),
    []
  );

  useEffect(() => {
    return () => {
      debouncedSetSearch.cancel();
    };
  }, [debouncedSetSearch]);

  useEffect(() => {
    setSelectedIndex(-1);
  }, [debouncedQuery, results.length]);

  useEffect(() => {
    const trimmedQuery = debouncedQuery.trim();
    if (!trimmedQuery) {
      setResults([]);
      setErrorMessage(null);
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();

    const fetchResults = async () => {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const response = await fetch(`${API_URL}?q=${encodeURIComponent(trimmedQuery)}`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Search failed (${response.status})`);
        }
        const data: SearchEntity[] = await response.json();
        setResults(data);
      } catch (error) {
        if ((error as Error).name === "AbortError") {
          return;
        }
        setErrorMessage("Unable to reach backend search service. Please check if the API is running.");
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    };

    void fetchResults();

    return () => {
      controller.abort();
    };
  }, [debouncedQuery]);

  const handleInputChange = (value: string) => {
    setQuery(value);
    debouncedSetSearch(value.trim());
  };

  const clearSearch = () => {
    setQuery("");
    setDebouncedQuery("");
    setResults([]);
    setErrorMessage(null);
    setIsLoading(false);
    debouncedSetSearch.cancel();
  };

  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!results.length) {
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % results.length);
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedIndex((prev) => (prev <= 0 ? results.length - 1 : prev - 1));
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100 [font-family:Inter,system-ui,sans-serif]">
      <div className="mx-auto w-full max-w-4xl rounded-2xl border border-slate-800 bg-slate-900/40 p-6 shadow-2xl shadow-slate-950/60 backdrop-blur-sm">
        <header className="mb-8 border-b border-slate-800 pb-4">
          <p className="text-xs uppercase tracking-[0.24em] text-cyan-400">Compliance Intelligence</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">Sanctions Scanner</h1>
        </header>

        <section className="mx-auto mb-8 w-full max-w-3xl">
          <div className="group flex items-center gap-3 rounded-2xl border border-slate-700/80 bg-slate-900/80 px-5 py-4 shadow-lg shadow-slate-950/50 backdrop-blur-md transition focus-within:border-cyan-400/70 focus-within:shadow-[0_0_0_3px_rgba(34,211,238,0.15)]">
            <Search className="h-5 w-5 text-slate-400" aria-hidden="true" />
            <input
              id="entity-search"
              type="text"
              value={query}
              onChange={(event) => handleInputChange(event.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="Search name, alias, IMO, country, or program..."
              className="w-full bg-transparent text-lg text-slate-100 outline-none placeholder:text-slate-500"
            />
            {query ? (
              <button
                type="button"
                onClick={clearSearch}
                className="inline-flex items-center gap-1 rounded-md border border-slate-600 px-2.5 py-1.5 text-sm text-slate-200 hover:border-slate-500 hover:bg-slate-800"
              >
                <X className="h-4 w-4" />
                Clear
              </button>
            ) : null}
          </div>
          <p className="mt-2 text-sm text-slate-400">
            Search runs after 300ms pause. Backend: <span className="font-mono text-slate-300">/api/search</span>
          </p>
        </section>

        {isLoading ? (
          <p className="mb-4 rounded-lg border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-300">
            Searching...
          </p>
        ) : null}

        {errorMessage ? (
          <p className="mb-4 rounded-lg border border-red-600 bg-red-950/70 px-4 py-3 text-sm text-red-200">
            {errorMessage}
          </p>
        ) : null}

        {!isLoading && debouncedQuery && !errorMessage && results.length === 0 ? (
          <p className="mb-4 rounded-lg border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-300">
            No matches found for <span className="font-semibold text-slate-100">"{debouncedQuery}"</span>.
          </p>
        ) : null}

        <section className="space-y-4">
          {results.map((entity, index) => {
            const Icon = getEntityIcon(entity.type);
            const isPerfectScore = entity.search_score >= 100;
            const isSelected = index === selectedIndex;

            return (
              <article
                key={entity.id}
                className={`mb-4 rounded-2xl border bg-slate-900/50 p-8 shadow-md shadow-slate-950/40 transition-all duration-200 hover:-translate-y-0.5 hover:border-slate-600 hover:shadow-lg ${
                  isSelected ? "border-cyan-400 ring-2 ring-cyan-500/40" : "border-slate-800"
                }`}
              >
                {entity.collision_warning ? (
                  <div className="mb-5 flex items-start gap-2 rounded-lg border border-red-400/90 bg-red-950/60 p-4 text-red-100 shadow-[0_0_24px_rgba(239,68,68,0.18)]">
                    <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
                    <div>
                      <p className="font-semibold uppercase tracking-wide text-red-300">Conflict Alert</p>
                      <p className="text-sm">{entity.collision_warning}</p>
                    </div>
                  </div>
                ) : null}

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg border border-slate-700 bg-slate-800 p-2">
                      <Icon className="h-5 w-5 text-cyan-300" />
                    </div>
                    <div>
                      <h2 className="text-xl font-bold text-slate-50">{highlightText(entity.name, debouncedQuery)}</h2>
                      <p className="text-sm text-slate-400">
                        Matched via: <span className="text-slate-200">{formatMatchType(entity.match_type)}</span>
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {entity.is_recent ? (
                      <span className="rounded-full border border-blue-400/70 bg-blue-900/60 px-2 py-0.5 text-xs font-semibold tracking-wide text-blue-100">
                        NEW
                      </span>
                    ) : null}
                    <span
                      className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${
                        isPerfectScore
                          ? "border-emerald-400/70 bg-emerald-900/40 text-emerald-200"
                          : "border-amber-400/70 bg-amber-900/40 text-amber-200"
                      }`}
                    >
                      {entity.search_score.toFixed(1)}%
                    </span>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded border border-slate-600 bg-slate-800 px-2 py-1 font-mono text-slate-200">
                    {entity.id}
                  </span>
                  {entity.programs.map((program) => (
                    <span key={`${entity.id}-program-${program}`} className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-slate-300">
                      {program}
                    </span>
                  ))}
                  {entity.countries.map((country) => (
                    <span key={`${entity.id}-country-${country}`} className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-slate-300">
                      {country}
                    </span>
                  ))}
                </div>

                {entity.remarks ? (
                  <p className="mt-3 text-sm text-slate-300">{highlightText(entity.remarks, debouncedQuery)}</p>
                ) : null}
              </article>
            );
          })}
        </section>
      </div>
    </main>
  );
}
