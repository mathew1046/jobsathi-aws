"""
tests/test_onboarding_agent.py
==============================
Unit + integration tests for the Onboarding Agent.

Test strategy
─────────────
The Onboarding Agent has two types of logic:

1. Pure Python logic — can be tested without any network/DB:
   • ONBOARDING_QUESTIONS structure (20 entries, unique keys, etc.)
   • Data-extraction parsing (json.loads branch vs. string branch)
   • save_profile_field field-column mapping
   • Session state updates inside handle_onboarding_message

2. Integration logic — requires a real (or mocked) PostgreSQL + Bedrock:
   • end-to-end handle_onboarding_message flow
   • DB writes via save_profile_field
   • Bedrock extraction via extract_data_from_answer
   • Translation fetch via get_question_text

The tests below are split accordingly.
  - Unit tests: no external dependencies, run with `pytest` immediately.
  - Integration tests: marked with @pytest.mark.integration — require a
    real DB + Bedrock (or mocked versions). Run with:
        pytest -m integration

How to run all unit tests (no DB or AWS needed):
    pip install pytest pytest-asyncio
    cd backend
    pytest tests/test_onboarding_agent.py -v -m "not integration"

How to run integration tests (needs .env with DB + AWS credentials):
    pytest tests/test_onboarding_agent.py -v -m integration
"""

import json
import sys
import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ── Make sure `backend/` is on the Python path ────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.onboarding_agent import (
    ONBOARDING_QUESTIONS,
    _Q_BY_INDEX,
    _FIELD_COLUMN_MAP,
    extract_data_from_answer,
    generate_next_question,
    handle_onboarding_message,
    save_profile_field,
    complete_onboarding,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def make_fresh_session(language: str = "hi") -> dict:
    """Returns a brand-new session dict identical to what create_new_session produces."""
    return {
        "worker_id": "test-worker-uuid",
        "phone_number": "+919999999999",
        "session_id": "test-session-uuid",
        "current_agent": "onboarding",
        "language": language,
        "onboarding": {
            "questions_answered": 0,
            "current_question_index": 0,
            "collected_data": {},
            "complete": False,
        },
        "matching": {
            "last_results": [],
            "current_job_index": 0,
            "active_search": None,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — no network, no DB
# ═══════════════════════════════════════════════════════════════════════════════


class TestQuestionsCatalogue:
    """Validate the static ONBOARDING_QUESTIONS structure."""

    def test_exactly_20_questions(self):
        assert len(ONBOARDING_QUESTIONS) == 20, (
            f"Expected 20 questions, got {len(ONBOARDING_QUESTIONS)}"
        )

    def test_indexes_are_0_to_19(self):
        indexes = [q["index"] for q in ONBOARDING_QUESTIONS]
        assert indexes == list(range(20)), f"Indexes not sequential 0-19: {indexes}"

    def test_all_have_field_key(self):
        for q in ONBOARDING_QUESTIONS:
            assert q.get("key"), f"Question {q['index']} missing 'key'"

    def test_all_have_extraction_hint(self):
        for q in ONBOARDING_QUESTIONS:
            assert q.get("extraction_hint"), (
                f"Question {q['index']} missing 'extraction_hint'"
            )

    def test_field_keys_are_unique(self):
        keys = [q["key"] for q in ONBOARDING_QUESTIONS]
        assert len(keys) == len(set(keys)), f"Duplicate field keys: {keys}"

    def test_q_by_index_lookup(self):
        """_Q_BY_INDEX must have an entry for every question index."""
        for i in range(20):
            assert i in _Q_BY_INDEX, f"Question index {i} missing from _Q_BY_INDEX"

    def test_expected_field_keys_present(self):
        """Critical fields must be present — these power the DB write logic."""
        required_keys = {
            "primary_skill",
            "secondary_skills",
            "years_experience",
            "city",
            "state",
            "willing_to_relocate",
            "availability",
            "expected_daily_wage",
            "name",
            "resume_consent",
        }
        actual_keys = {q["key"] for q in ONBOARDING_QUESTIONS}
        missing = required_keys - actual_keys
        assert not missing, f"Required field keys missing: {missing}"

    def test_resume_consent_is_last(self):
        """resume_consent must be the last question (index 19) to trigger completion."""
        last_q = ONBOARDING_QUESTIONS[-1]
        assert last_q["key"] == "resume_consent", (
            f"Last question should be resume_consent, got {last_q['key']}"
        )

    def test_primary_skill_is_first(self):
        """primary_skill must be first — it's the most critical data point."""
        first_q = ONBOARDING_QUESTIONS[0]
        assert first_q["key"] == "primary_skill", (
            f"First question should be primary_skill, got {first_q['key']}"
        )


class TestFieldColumnMap:
    """Validate that _FIELD_COLUMN_MAP covers essential profile columns."""

    def test_primary_skill_mapped(self):
        assert _FIELD_COLUMN_MAP.get("primary_skill") == "primary_skill"

    def test_questions_answered_mapped(self):
        assert _FIELD_COLUMN_MAP.get("questions_answered") == "questions_answered"

    def test_profile_complete_mapped(self):
        assert _FIELD_COLUMN_MAP.get("profile_complete") == "profile_complete"

    def test_no_sql_injection_in_keys(self):
        """Column names must be safe identifiers."""
        import re

        safe_pattern = re.compile(r"^[a-z_]+$")
        for key, col in _FIELD_COLUMN_MAP.items():
            assert safe_pattern.match(col), (
                f"Unsafe column name for key '{key}': '{col}'"
            )


class TestExtractDataParsing:
    """
    Test the JSON/string parsing branch in extract_data_from_answer WITHOUT
    calling Bedrock — we patch get_bedrock_client so it's never called.
    """

    def _make_bedrock_mock(self, return_text: str):
        """Returns a mock bedrock client whose invoke_model returns return_text."""
        mock_response_body = MagicMock()
        mock_response_body.read.return_value = json.dumps(
            {"content": [{"text": return_text}]}
        ).encode()
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = {"body": mock_response_body}
        return mock_bedrock

    @pytest.mark.asyncio
    async def test_extracts_integer_from_json(self):
        mock_bedrock = self._make_bedrock_mock("7")
        with patch(
            "agents.onboarding_agent.get_bedrock_client", return_value=mock_bedrock
        ):
            question = _Q_BY_INDEX[2]  # years_experience
            result = await extract_data_from_answer(
                question, "saat saal se kaam kar raha hoon", "hi"
            )
        assert result == 7

    @pytest.mark.asyncio
    async def test_extracts_bool_true_from_json(self):
        mock_bedrock = self._make_bedrock_mock("true")
        with patch(
            "agents.onboarding_agent.get_bedrock_client", return_value=mock_bedrock
        ):
            question = _Q_BY_INDEX[6]  # willing_to_relocate
            result = await extract_data_from_answer(
                question, "haan, ja sakta hoon", "hi"
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_extracts_bool_false_from_json(self):
        mock_bedrock = self._make_bedrock_mock("false")
        with patch(
            "agents.onboarding_agent.get_bedrock_client", return_value=mock_bedrock
        ):
            question = _Q_BY_INDEX[6]
            result = await extract_data_from_answer(
                question, "nahi, yahan rehna chahta hoon", "hi"
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_extracts_list_from_json(self):
        mock_bedrock = self._make_bedrock_mock('["whitewash", "waterproofing"]')
        with patch(
            "agents.onboarding_agent.get_bedrock_client", return_value=mock_bedrock
        ):
            question = _Q_BY_INDEX[1]  # secondary_skills
            result = await extract_data_from_answer(
                question, "whitewash aur waterproofing bhi karta hoon", "hi"
            )
        assert result == ["whitewash", "waterproofing"]

    @pytest.mark.asyncio
    async def test_extracts_string_city(self):
        mock_bedrock = self._make_bedrock_mock("Pune")
        with patch(
            "agents.onboarding_agent.get_bedrock_client", return_value=mock_bedrock
        ):
            question = _Q_BY_INDEX[3]  # city
            result = await extract_data_from_answer(
                question, "main Pune mein rehta hoon", "hi"
            )
        assert result == "Pune"

    @pytest.mark.asyncio
    async def test_null_returns_none(self):
        mock_bedrock = self._make_bedrock_mock("null")
        with patch(
            "agents.onboarding_agent.get_bedrock_client", return_value=mock_bedrock
        ):
            question = _Q_BY_INDEX[12]  # name (optional)
            result = await extract_data_from_answer(question, "nahi batana", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_list_returned_as_list(self):
        mock_bedrock = self._make_bedrock_mock("[]")
        with patch(
            "agents.onboarding_agent.get_bedrock_client", return_value=mock_bedrock
        ):
            question = _Q_BY_INDEX[15]  # certifications
            result = await extract_data_from_answer(
                question, "koi certificate nahi hai", "hi"
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_availability_immediate(self):
        mock_bedrock = self._make_bedrock_mock("immediate")
        with patch(
            "agents.onboarding_agent.get_bedrock_client", return_value=mock_bedrock
        ):
            question = _Q_BY_INDEX[8]
            result = await extract_data_from_answer(
                question, "abhi kaam nahi hai, dhundh raha hoon", "hi"
            )
        assert result == "immediate"


class TestSessionStateManagement:
    """
    Test the state machine inside handle_onboarding_message using full mocks.
    No DB, no Bedrock, no Redis.
    """

    def _mock_all_externals(self, bedrock_return: str, question_db_return: str):
        """
        Returns a context manager that patches all external calls.
        """
        mock_response_body = MagicMock()
        mock_response_body.read.return_value = json.dumps(
            {"content": [{"text": bedrock_return}]}
        ).encode()
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = {"body": mock_response_body}

        patches = [
            patch(
                "agents.onboarding_agent.get_bedrock_client", return_value=mock_bedrock
            ),
            patch(
                "agents.onboarding_agent.get_question_text",
                new=AsyncMock(return_value=question_db_return),
            ),
            patch("agents.onboarding_agent.save_profile_field", new=AsyncMock()),
            patch(
                "agents.onboarding_agent.get_recent_conversation",
                new=AsyncMock(return_value=[]),
            ),
        ]
        return patches

    @pytest.mark.asyncio
    async def test_first_message_asks_question_0(self):
        """First interaction (index=0) should include the first question text."""
        session = make_fresh_session("hi")

        patches = self._mock_all_externals(
            bedrock_return="tile_work",
            question_db_return="आप कौन सा काम करते हैं?",
        )
        with patches[0], patches[1], patches[2], patches[3]:
            response, updated_session = await handle_onboarding_message(
                text="", session=session, worker_id="w1", phone_number="+91999"
            )

        assert "आप कौन सा काम करते हैं?" in response
        assert updated_session["onboarding"]["current_question_index"] == 1

    @pytest.mark.asyncio
    async def test_question_index_advances_each_turn(self):
        """Each call should advance the question index by exactly 1."""
        session = make_fresh_session("en")

        for expected_index in range(1, 5):
            session["onboarding"]["current_question_index"] = expected_index - 1
            patches = self._mock_all_externals(
                bedrock_return="some_value",
                question_db_return="Question text",
            )
            with patches[0], patches[1], patches[2], patches[3]:
                _, session = await handle_onboarding_message(
                    text="some answer",
                    session=session,
                    worker_id="w1",
                    phone_number="+91999",
                )
            assert session["onboarding"]["current_question_index"] == expected_index, (
                f"Expected index {expected_index}, got {session['onboarding']['current_question_index']}"
            )

    @pytest.mark.asyncio
    async def test_collected_data_updated_after_each_answer(self):
        """Data extracted from an answer must land in session collected_data."""
        session = make_fresh_session("hi")
        session["onboarding"]["current_question_index"] = (
            1  # answering question 0 (primary_skill)
        )

        patches = self._mock_all_externals(
            bedrock_return="electrical",
            question_db_return="Question text",
        )
        with patches[0], patches[1], patches[2], patches[3]:
            _, updated = await handle_onboarding_message(
                text="bijli ka kaam karta hoon",
                session=session,
                worker_id="w1",
                phone_number="+91999",
            )

        assert (
            updated["onboarding"]["collected_data"].get("primary_skill") == "electrical"
        )

    @pytest.mark.asyncio
    async def test_complete_onboarding_switches_agent(self):
        """When index reaches 20, the agent should switch to 'matching'."""
        session = make_fresh_session("hi")
        session["onboarding"]["current_question_index"] = 20  # all answered

        mock_conn = AsyncMock()
        mock_pool_obj = MagicMock()
        mock_pool_obj.acquire = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=None),
            )
        )

        with (
            patch("agents.onboarding_agent.save_profile_field", new=AsyncMock()),
            patch(
                "agents.onboarding_agent.generate_resume_pdf",
                new=AsyncMock(return_value="s3/key"),
            ),
            patch(
                "agents.onboarding_agent.get_question_text",
                new=AsyncMock(return_value="previous question?"),
            ),
            patch(
                "agents.onboarding_agent.get_pool",
                new=AsyncMock(return_value=mock_pool_obj),
            ),
        ):
            _, updated = await handle_onboarding_message(
                text="haan, resume banao",
                session=session,
                worker_id="w1",
                phone_number="+91999",
            )

        assert updated["current_agent"] == "matching"
        assert updated["onboarding"]["complete"] is True

    @pytest.mark.asyncio
    async def test_null_extraction_does_not_save_to_session(self):
        """If Bedrock returns null, collected_data should NOT be updated."""
        session = make_fresh_session("hi")
        session["onboarding"]["current_question_index"] = (
            13  # answering name (index 12)
        )

        patches = self._mock_all_externals(
            bedrock_return="null",  # worker declined to share name
            question_db_return="Your biggest project?",
        )
        with patches[0], patches[1], patches[2], patches[3]:
            _, updated = await handle_onboarding_message(
                text="nahi batana",
                session=session,
                worker_id="w1",
                phone_number="+91999",
            )

        # "name" should NOT appear in collected_data (value was null)
        assert (
            "name" not in updated["onboarding"]["collected_data"]
            or updated["onboarding"]["collected_data"].get("name") is None
        )


class TestSaveProfileField:
    """
    Test save_profile_field with a mocked asyncpg connection pool.
    """

    def _make_pool_mock(self):
        """Returns (mock_conn, mock_pool_obj) where pool_obj.acquire() is mocked."""
        mock_conn = AsyncMock()
        mock_pool_obj = MagicMock()
        mock_pool_obj.acquire = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        return mock_conn, mock_pool_obj

    @pytest.mark.asyncio
    async def test_skips_none_values(self):
        """Saving None should be a no-op — no DB call."""
        with patch("agents.onboarding_agent.get_pool") as mock_get_pool:
            await save_profile_field("worker1", "city", None)
            mock_get_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_saves_scalar_field(self):
        """A simple string field should fire an INSERT + UPDATE."""
        mock_conn, mock_pool_obj = self._make_pool_mock()

        with patch(
            "agents.onboarding_agent.get_pool",
            new=AsyncMock(return_value=mock_pool_obj),
        ):
            await save_profile_field("worker1", "city", "Pune")

        # Two execute calls: INSERT ON CONFLICT + UPDATE
        assert mock_conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_saves_list_secondary_skills(self):
        """secondary_skills (list) should use the array UPDATE branch."""
        mock_conn, mock_pool_obj = self._make_pool_mock()

        with patch(
            "agents.onboarding_agent.get_pool",
            new=AsyncMock(return_value=mock_pool_obj),
        ):
            await save_profile_field(
                "worker1", "secondary_skills", ["whitewash", "waterproofing"]
            )

        assert mock_conn.execute.call_count == 2  # INSERT + UPDATE array
        # Check the UPDATE call references secondary_skills
        update_call_args = mock_conn.execute.call_args_list[1][0]
        assert "secondary_skills" in update_call_args[0]

    @pytest.mark.asyncio
    async def test_unknown_field_key_is_ignored(self):
        """A field_key not in _FIELD_COLUMN_MAP should not blow up."""
        mock_conn, mock_pool_obj = self._make_pool_mock()

        with patch(
            "agents.onboarding_agent.get_pool",
            new=AsyncMock(return_value=mock_pool_obj),
        ):
            # Should not raise; just INSERT ON CONFLICT, no UPDATE
            await save_profile_field("worker1", "unknown_field_xyz", "some_value")

        # Only the INSERT ON CONFLICT should fire, no UPDATE
        assert mock_conn.execute.call_count == 1


class TestQuestionTranslationCoverage:
    """
    Validates the seed_questions.py data (imported directly) to ensure
    every question has translations for all 10 languages and no empty strings.
    """

    # Import the QUESTIONS list directly from the seed module
    @pytest.fixture(autouse=True, scope="class")
    def import_seed(self):
        import importlib.util

        seed_path = os.path.join(os.path.dirname(__file__), "..", "seed_questions.py")
        spec = importlib.util.spec_from_file_location("seed_questions", seed_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.__class__.SEED_QUESTIONS = mod.QUESTIONS
        self.__class__.SEED_LANGUAGES = mod.LANGUAGES

    def test_seed_has_20_questions(self):
        assert len(self.SEED_QUESTIONS) == 20

    def test_all_questions_have_all_languages(self):
        lang_codes = {code for code, _ in self.SEED_LANGUAGES}
        for q in self.SEED_QUESTIONS:
            for code in lang_codes:
                assert code in q["translations"], (
                    f"Question {q['index']} ({q['field_key']}) missing translation for '{code}'"
                )

    def test_no_empty_translations(self):
        for q in self.SEED_QUESTIONS:
            for code, text in q["translations"].items():
                assert text and text.strip(), (
                    f"Question {q['index']} has empty translation for '{code}'"
                )

    def test_10_languages_defined(self):
        assert len(self.SEED_LANGUAGES) == 10

    def test_language_codes_match_onboarding_agent(self):
        """Language codes in seed must match what the voice agent supports."""
        seed_codes = {code for code, _ in self.SEED_LANGUAGES}
        expected_codes = {"hi", "ta", "te", "mr", "bn", "gu", "kn", "pa", "ml", "en"}
        assert seed_codes == expected_codes

    def test_seed_field_keys_match_agent(self):
        """field_key in seed must match the ONBOARDING_QUESTIONS key in the agent."""
        seed_keys = [q["field_key"] for q in self.SEED_QUESTIONS]
        agent_keys = [q["key"] for q in ONBOARDING_QUESTIONS]
        assert seed_keys == agent_keys, (
            f"Mismatch between seed field_keys and agent keys.\n"
            f"Seed:  {seed_keys}\n"
            f"Agent: {agent_keys}"
        )

    def test_seed_indexes_match_agent(self):
        """Indexes in seed must match ONBOARDING_QUESTIONS indexes."""
        seed_indexes = [q["index"] for q in self.SEED_QUESTIONS]
        agent_indexes = [q["index"] for q in ONBOARDING_QUESTIONS]
        assert seed_indexes == agent_indexes


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — require real PostgreSQL + AWS (marked separately)
# Run with: pytest -m integration
# ═══════════════════════════════════════════════════════════════════════════════

pytestmark_integration = pytest.mark.integration


@pytest.mark.integration
class TestDatabaseTranslationLookup:
    """
    Tests that run against a real database.
    Require DB_HOST / DB_NAME / DB_USER / DB_PASSWORD in environment.
    Seed must have been run first: python seed_questions.py
    """

    @pytest.mark.asyncio
    async def test_get_question_text_hindi(self):
        from core.database import get_question_text, create_all_tables

        await create_all_tables()
        text = await get_question_text(0, "hi")
        assert text is not None
        assert len(text) > 5
        # Hindi question 0 should be about skill
        assert "काम" in text or "skill" in text.lower()

    @pytest.mark.asyncio
    async def test_get_question_text_tamil(self):
        from core.database import get_question_text

        text = await get_question_text(0, "ta")
        assert text is not None
        assert len(text) > 5

    @pytest.mark.asyncio
    async def test_get_all_questions_returns_20(self):
        from core.database import get_all_questions_for_language

        questions = await get_all_questions_for_language("hi")
        assert len(questions) == 20

    @pytest.mark.asyncio
    async def test_fallback_to_english_for_unknown_language(self):
        from core.database import get_question_text

        # "xx" is not a real language code — should fall back to English
        text = await get_question_text(0, "xx")
        assert text is not None  # English fallback
        assert "work" in text.lower() or "skill" in text.lower()

    @pytest.mark.asyncio
    async def test_all_10_languages_have_question_0(self):
        from core.database import get_question_text

        languages = ["hi", "ta", "te", "mr", "bn", "gu", "kn", "pa", "ml", "en"]
        for lang in languages:
            text = await get_question_text(0, lang)
            assert text, f"No question text for language '{lang}'"


@pytest.mark.integration
class TestFullOnboardingFlow:
    """
    Full end-to-end test of handle_onboarding_message using a real DB
    but a mocked Bedrock (to avoid LLM costs in CI).
    """

    @pytest.mark.asyncio
    async def test_20_question_flow_completes(self):
        """
        Simulates a complete 20-question onboarding conversation.
        After 20 turns the session agent should switch to 'matching'.
        """
        from core.database import create_all_tables, get_or_create_worker

        await create_all_tables()
        worker = await get_or_create_worker("+919000000001")
        worker_id = str(worker["id"])
        session = make_fresh_session("hi")
        session["worker_id"] = worker_id

        # Fake answers that Bedrock would extract — one per question
        fake_extractions = [
            "tile_work",  # 0 primary_skill
            '["whitewash"]',  # 1 secondary_skills
            "8",  # 2 years_experience
            "Pune",  # 3 city
            "Shivajinagar",  # 4 district
            "Maharashtra",  # 5 state
            "true",  # 6 willing_to_relocate
            "50",  # 7 max_travel_km
            "immediate",  # 8 availability
            "600",  # 9 expected_daily_wage
            "daily_wage",  # 10 work_type
            "8am-5pm",  # 11 preferred_hours
            "Ramesh Kumar",  # 12 name
            "Worked on a 200 unit apartment",  # 13 biggest_project
            "L&T Construction",  # 14 previous_employer
            '["ITI"]',  # 15 certifications
            '["drill machine", "grinder"]',  # 16 tools_equipment
            "Very precise tile cutting",  # 17 special_skills
            "I have 8 years of tile laying exp",  # 18 skill_description
            "true",  # 19 resume_consent
        ]

        # We'll feed one fake extraction per question turn
        extraction_iter = iter(fake_extractions)

        def make_bedrock_mock(text: str):
            body = MagicMock()
            body.read.return_value = json.dumps({"content": [{"text": text}]}).encode()
            bedrock = MagicMock()
            bedrock.invoke_model.return_value = {"body": body}
            return bedrock

        for turn in range(20):
            extraction_text = next(extraction_iter)
            bedrock_mock = make_bedrock_mock(extraction_text)

            with (
                patch(
                    "agents.onboarding_agent.get_bedrock_client",
                    return_value=bedrock_mock,
                ),
                patch(
                    "agents.onboarding_agent.generate_resume_pdf",
                    new=AsyncMock(return_value="s3/key"),
                ),
                patch(
                    "agents.onboarding_agent.get_pool"
                ) as _pool_mock,  # skip actual DB write in unit
            ):
                mock_conn = AsyncMock()
                _pool_mock.return_value = MagicMock()
                _pool_mock.return_value.acquire = MagicMock(
                    return_value=MagicMock(
                        __aenter__=AsyncMock(return_value=mock_conn),
                        __aexit__=AsyncMock(return_value=None),
                    )
                )

                # We still need get_question_text from the real DB
                response, session = await handle_onboarding_message(
                    text=f"answer for question {turn}",
                    session=session,
                    worker_id=worker_id,
                    phone_number="+919000000001",
                )

            assert response, f"Empty response on turn {turn}"

        # After all 20 questions, agent should switch to matching
        assert session["current_agent"] == "matching", (
            f"Expected 'matching', got '{session['current_agent']}'"
        )
        assert session["onboarding"]["complete"] is True
