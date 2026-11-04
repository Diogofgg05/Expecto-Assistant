"""Adaptive, offline practice with independent, deterministic scoring.

This tracks demonstrated performance *on generated exercises*, not the LLM's
intelligence or accuracy. No model is invoked and no automatic weight changes,
web access, code execution, or unrequested background work occurs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from random import Random
from secrets import randbelow
from uuid import uuid4
import re

DOMAINS = ("matematica", "programacao", "fisica")
LABELS = {"matematica": "Matemática", "programacao": "Programação",
          "fisica": "Física"}
MAX_AGE = timedelta(hours=24)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate(domain: str, level: int, seed: int) -> tuple[str, str, str]:
    """Generate questions and independent numeric answers without eval/exec."""
    if domain not in DOMAINS or type(level) is not int or not 1 <= level <= 3:
        raise ValueError("Área ou dificuldade desconhecida")
    rng = Random(seed)
    if domain == "matematica":
        if level == 1:
            a, b, c = rng.randint(2, 15), rng.randint(2, 12), rng.randint(-9, 9)
            return (f"Calcula {a} × {b} + ({c}). Responde só com o inteiro.",
                    str(a * b + c), f"{a} × {b} + ({c}) = {a * b + c}.")
        if level == 2:
            a, b, c, d = [rng.randint(-8, 9) for _ in range(4)]
            return (f"Determina det([[{a},{b}],[{c},{d}]]). Responde só com o inteiro.",
                    str(a * d - b * c), f"det = {a}×{d} - {b}×{c} = {a*d-b*c}.")
        x, y = rng.randint(-10, 10), rng.randint(-10, 10)
        return (f"Resolve x+y={x+y} e 2x+y={2*x+y}. Responde x,y sem espaços.",
                f"{x},{y}", f"Subtraindo as equações obténs x={x}, logo y={y}.")
    if domain == "programacao":
        if level == 1:
            a, b = rng.randint(3, 40), rng.randint(2, 9)
            return (f"Qual é a saída de Python: print({a} // {b})? Responde só com o inteiro.",
                    str(a // b), f"A divisão inteira resulta em {a // b}.")
        if level == 2:
            start, count, step = rng.randint(-5, 5), rng.randint(3, 8), rng.randint(1, 4)
            stop = start + count * step
            total = sum(start + i * step for i in range(count))
            return (f"Qual é a saída de Python: print(sum(range({start}, {stop}, {step})))? "
                    "Responde só com o inteiro.", str(total),
                    f"A soma dos {count} valores da progressão é {total}.")
        values = [rng.randint(-9, 15) for _ in range(6)]
        total = sum(n for n in values if n % 2 == 0)
        return (f"Em Python, calcula sum(n for n in {values} if n % 2 == 0). "
                "Responde só com o inteiro.", str(total),
                f"A soma dos valores pares é {total}.")
    if level == 1:
        t, velocity = rng.randint(2, 10), rng.randint(3, 19)
        return (f"Um móvel percorre {t*velocity} m em {t} s a velocidade constante. "
                "Qual é a velocidade em m/s? Responde só com o inteiro.",
                str(velocity), f"v = distância/tempo = {t*velocity}/{t} = {velocity} m/s.")
    if level == 2:
        mass, acceleration = rng.randint(2, 25), rng.randint(2, 12)
        return (f"Uma massa de {mass} kg acelera a {acceleration} m/s². "
                "Qual é a força resultante em N? Responde só com o inteiro.",
                str(mass * acceleration),
                f"F = m×a = {mass}×{acceleration} = {mass*acceleration} N.")
    mass, velocity = 2*rng.randint(1, 12), rng.randint(2, 15)
    energy = mass * velocity * velocity // 2
    return (f"Um corpo de {mass} kg move-se a {velocity} m/s. "
            "Calcula a energia cinética em J (E=mv²/2). Responde só com o inteiro.",
            str(energy),
            f"E = {mass}×{velocity}²/2 = {energy} J.")


def normalized_answer(answer: str) -> str:
    if not isinstance(answer, str):
        raise ValueError("A resposta tem de ser texto")
    value = re.sub(r"\s*,\s*", ",", answer.strip())
    if not re.fullmatch(r"[+-]?\d{1,8}(?:,[+-]?\d{1,8})?", value):
        raise ValueError("Responde apenas com um inteiro ou com dois inteiros x,y")
    return ",".join(str(int(n)) for n in value.split(","))


class CompetencyEngine:
    """One pending challenge per local database; no hidden scoring via a model."""

    def __init__(self, db):
        self.db = db
        with db.connect() as conn:
            self.migrate(conn)

    @staticmethod
    def migrate(conn):
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS expecto_practice (
            id TEXT PRIMARY KEY,
            domain TEXT NOT NULL CHECK(domain IN ('matematica','programacao','fisica')),
            level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 3),
            question TEXT NOT NULL, solution TEXT NOT NULL, explanation TEXT NOT NULL,
            created_at TEXT NOT NULL, status TEXT NOT NULL
                CHECK(status IN ('pending','answered','skipped')),
            answered_at TEXT, user_answer TEXT, correct INTEGER
                CHECK(correct IN (0,1) OR correct IS NULL)
        );
        CREATE INDEX IF NOT EXISTS ix_expecto_practice_domain
            ON expecto_practice(domain, status, answered_at);
        CREATE UNIQUE INDEX IF NOT EXISTS ix_expecto_practice_one_pending
            ON expecto_practice(status) WHERE status='pending';
        """)

    @staticmethod
    def _recent(conn, domain):
        return [dict(r) for r in conn.execute(
            """SELECT level,correct FROM expecto_practice
               WHERE domain=? AND status='answered'
               ORDER BY answered_at DESC, rowid DESC LIMIT 8""", (domain,))]

    @staticmethod
    def _level(recent):
        if not recent:
            return 1
        level = recent[0]["level"]
        if len(recent) >= 4 and all(item["correct"] for item in recent[:4]):
            return min(3, level + 1)
        if len(recent) >= 3 and sum(item["correct"] for item in recent[:3]) <= 1:
            return max(1, level - 1)
        return level

    def _domain(self, conn):
        profiles = [self._recent(conn, domain) for domain in DOMAINS]
        # Collect initial evidence in each area before identifying a weakness.
        for index, items in enumerate(profiles):
            if len(items) < 3 and len(items) == min(len(p) for p in profiles):
                return DOMAINS[index]
        # Lowest verified practice accuracy; ties follow stable domain order.
        index = min(range(len(DOMAINS)), key=lambda i:
                    sum(x["correct"] for x in profiles[i]) / len(profiles[i]))
        return DOMAINS[index]

    @staticmethod
    def _public(row):
        # Never expose solution before it has been answered.
        return {"id": row["id"], "domain": row["domain"],
                "area": LABELS[row["domain"]], "level": row["level"],
                "question": row["question"], "status": "pending"}

    def next(self, domain: str | None = None, *, seed: int | None = None) -> dict:
        if domain is not None and domain not in DOMAINS:
            raise ValueError("Área desconhecida")
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            pending = conn.execute(
                "SELECT * FROM expecto_practice WHERE status='pending' LIMIT 1").fetchone()
            if pending is not None:
                created = datetime.fromisoformat(pending["created_at"])
                expired = utcnow() - created > MAX_AGE
                changed = domain is not None and domain != pending["domain"]
                if not expired and not changed:
                    return self._public(pending)
                conn.execute("UPDATE expecto_practice SET status='skipped' WHERE id=?",
                             (pending["id"],))
            selected = domain or self._domain(conn)
            level = self._level(self._recent(conn, selected))
            if seed is None:
                seed = randbelow(2**32)
            if type(seed) is not int or not 0 <= seed < 2**64:
                raise ValueError("Seed inválida")
            question, solution, explanation = generate(selected, level, seed)
            record = (uuid4().hex[:12], selected, level, question, solution,
                      explanation, utcnow().isoformat(), "pending")
            conn.execute("""INSERT INTO expecto_practice
                (id,domain,level,question,solution,explanation,created_at,status)
                VALUES (?,?,?,?,?,?,?,?)""", record)
            return self._public(conn.execute(
                "SELECT * FROM expecto_practice WHERE id=?", (record[0],)).fetchone())

    def submit(self, ident: str, answer: str) -> dict:
        if not isinstance(ident, str) or not re.fullmatch(r"[a-f0-9]{12}", ident):
            raise ValueError("Identificador de exercício inválido")
        given = normalized_answer(answer)
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM expecto_practice WHERE id=?",
                               (ident,)).fetchone()
            if row is None:
                raise ValueError("Exercício desconhecido")
            if row["status"] != "pending":
                raise ValueError("Este exercício já foi encerrado")
            if utcnow() - datetime.fromisoformat(row["created_at"]) > MAX_AGE:
                conn.execute("UPDATE expecto_practice SET status='skipped' WHERE id=?",
                             (ident,))
                raise ValueError("O exercício expirou; pede outro")
            correct = int(given == row["solution"])
            conn.execute("""UPDATE expecto_practice SET status='answered',
                answered_at=?, user_answer=?, correct=? WHERE id=? AND status='pending'""",
                (utcnow().isoformat(), given, correct, ident))
            return {"id": ident, "domain": row["domain"],
                    "area": LABELS[row["domain"]], "level": row["level"],
                    "correct": bool(correct), "your_answer": given,
                    "solution": row["solution"], "explanation": row["explanation"],
                    "meaning": "Correção determinística de um exercício; não certifica competência geral."}

    def skip(self) -> bool:
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return conn.execute("""UPDATE expecto_practice SET status='skipped'
                WHERE status='pending'""").rowcount == 1

    def report(self) -> dict:
        with self.db.connect() as conn:
            rows = []
            for domain in DOMAINS:
                recent = self._recent(conn, domain)
                counts = conn.execute("""SELECT COUNT(*) AS total, COALESCE(SUM(correct),0) AS correct
                    FROM expecto_practice WHERE domain=? AND status='answered'""",
                    (domain,)).fetchone()
                rows.append({"domain": domain, "area": LABELS[domain],
                             "answered": counts["total"], "correct": counts["correct"],
                             "recent_accuracy": round(100 * sum(r["correct"] for r in recent) /
                                                       len(recent)) if recent else None,
                             "next_level": self._level(recent),
                             "sample_sufficient": len(recent) >= 3})
            pending = conn.execute(
                "SELECT id,domain FROM expecto_practice WHERE status='pending' LIMIT 1"
            ).fetchone()
            weakest = (self._domain(conn)
                       if any(r["answered"] for r in rows) else None)
        return {"domains": rows, "suggested_domain": weakest,
                "pending": dict(pending) if pending else None,
                "meaning": "Resultados em exercícios gerados; não há treino dos pesos do modelo.",
                "automatic_model_training": False}
