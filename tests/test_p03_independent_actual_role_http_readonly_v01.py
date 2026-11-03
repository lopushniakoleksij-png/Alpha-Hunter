"""Credential-free P0.3 role reviewer negative contracts."""
import importlib.util
import unittest
from pathlib import Path

SRC=Path(__file__).resolve().parents[1]/"ops/reviews/p03_independent_actual_supabase_role_http_readonly_v01.py"
spec=importlib.util.spec_from_file_location("p03_role_review",SRC)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

def fake(statuses):
    calls=[]
    def get(route,headers):
        calls.append((route,headers))
        return statuses[route]
    return get,calls

class P03RoleTests(unittest.TestCase):
    def test_no_key_denied_status_only(self):
        cases={path:(401,b'{"error":"untrusted"}') for _,path in a.ROUTES}
        get,calls=fake(cases)
        result=a.run("no-key",env={},get=get)
        self.assertTrue(result["all_checks_passed"])
        self.assertEqual(len(calls),3)
        self.assertTrue(all(x[1].get("apikey") is None for x in calls))
        self.assertFalse(result["production_release_authorized"])

    def test_no_key_unexpected_public_success_is_rejected(self):
        cases={path:(200,b'[]') for _,path in a.ROUTES}
        get,_=fake(cases)
        self.assertEqual(a.run("no-key",env={},get=get)["status"],"BLOCKED_ROLE_API_MISMATCH")

    def test_anon_no_credentials_fails_before_http(self):
        get,calls=fake({})
        with self.assertRaises(RuntimeError):
            a.run("anon",env={"AH_P03_EXPLICIT_API_REVIEW":"1"},get=get)
        self.assertEqual(calls,[])

    def test_role_authorization_opt_in_mandatory(self):
        get,calls=fake({})
        with self.assertRaises(RuntimeError):
            a.run("service_role",env={"AH_P03_PRIVILEGED_REVIEW_KEY":"sb_secret_x"},
                  get=get)
        self.assertEqual(calls,[])

    def test_privileged_explicit_separate_authorization(self):
        get,calls=fake({})
        with self.assertRaises(RuntimeError):
            a.run("service_role",env={"AH_P03_EXPLICIT_API_REVIEW":"1",
                  "AH_P03_PRIVILEGED_REVIEW_KEY":"sb_secret_example"},get=get)
        self.assertEqual(calls,[])

    def test_anon_expected_empty_rls_and_protected_table_denial(self):
        env={"AH_P03_EXPLICIT_API_REVIEW":"1","AH_P03_PUBLISHABLE_KEY":"sb_publishable_synthetic"}
        cases={p:(200,b"[]") for k,p in a.ROUTES if k!="exit"}
        cases[next(p for k,p in a.ROUTES if k=="exit")]=(403,b"not approved")
        get,calls=fake(cases)
        result=a.run("anon",env=env,get=get)
        self.assertTrue(result["all_checks_passed"])
        self.assertNotIn("sb_publishable_synthetic",str(result))
        self.assertFalse(result["independent_human_signoff"])
        self.assertEqual({x[1]["apikey"] for x in calls},{"sb_publishable_synthetic"})
        self.assertTrue(all(x[0].startswith("/") for x in calls))

    def test_anon_unexpected_sensitive_records_rejected(self):
        env={"AH_P03_EXPLICIT_API_REVIEW":"1","AH_P03_PUBLISHABLE_KEY":"sb_publishable_synthetic"}
        cases={p:(200,b"[]") for _,p in a.ROUTES}
        cases[a.ROUTES[0][1]]=(200,b'[{"run_id":"should_be_private"}]')
        get,_=fake(cases)
        res=a.run("anon",env=env,get=get)
        self.assertEqual(res["status"],"BLOCKED_ROLE_API_MISMATCH")
        self.assertNotIn("should_be_private",str(res))

    def test_authenticated_requires_existing_jwt(self):
        env={"AH_P03_EXPLICIT_API_REVIEW":"1","AH_P03_PUBLISHABLE_KEY":"sb_publishable_synthetic"}
        get,calls=fake({})
        with self.assertRaises(RuntimeError):
            a.run("authenticated",env=env,get=get)
        self.assertEqual(calls,[])

    def test_expired_jwt_rejected_before_tables(self):
        env={"AH_P03_EXPLICIT_API_REVIEW":"1","AH_P03_PUBLISHABLE_KEY":"sb_publishable_synthetic",
             "AH_P03_AUTH_USER_ACCESS_TOKEN":"synthetic_user_jwt"}
        get,calls=fake({"/auth/v1/user":(401,b"expired")})
        out=a.run("authenticated",env=env,get=get)
        self.assertEqual(out["status"],"BLOCKED_INVALID_AUTHENTICATED_TOKEN")
        self.assertEqual(len(calls),1)

    def test_authenticated_valid_token_rls_zero_rows(self):
        env={"AH_P03_EXPLICIT_API_REVIEW":"1","AH_P03_PUBLISHABLE_KEY":"sb_publishable_synthetic",
             "AH_P03_AUTH_USER_ACCESS_TOKEN":"synthetic_user_jwt"}
        cases={"/auth/v1/user":(200,b'{"fake":"user"}')}
        cases.update({p:(200,b"[]") for k,p in a.ROUTES if k!="exit"})
        cases[a.ROUTES[2][1]]=(403,b"denied")
        get,_=fake(cases)
        out=a.run("authenticated",env=env,get=get)
        self.assertTrue(out["all_checks_passed"])
        self.assertNotIn("synthetic_user_jwt",str(out))

    def test_privileged_get_success_still_not_signoff(self):
        env={"AH_P03_EXPLICIT_API_REVIEW":"1",
             "AH_P03_PRIVILEGED_READ_AUTHORIZED":"1",
             "AH_P03_PRIVILEGED_REVIEW_KEY":"sb_secret_synthetic"}
        get,calls=fake({p:(200,b'[{"synthetic":"fixture"}]') for _,p in a.ROUTES})
        out=a.run("service_role",env=env,get=get)
        self.assertTrue(out["all_checks_passed"])
        self.assertFalse(out["reviewer_has_signed"])
        self.assertFalse(out["production_release_authorized"])
        self.assertNotIn("sb_secret_synthetic",str(out))
        self.assertTrue(all("Authorization" not in c[1] for c in calls))

    def test_legacy_service_key_uses_bearer_without_output(self):
        env={"AH_P03_EXPLICIT_API_REVIEW":"1",
             "AH_P03_PRIVILEGED_READ_AUTHORIZED":"1",
             "AH_P03_PRIVILEGED_REVIEW_KEY":"eyJsyntheticonly"}
        get,calls=fake({p:(200,b'[]') for _,p in a.ROUTES})
        out=a.run("service_role",env=env,get=get)
        self.assertTrue(out["all_checks_passed"])
        self.assertTrue(all(c[1]["Authorization"].startswith("Bearer eyJ") for c in calls))
        self.assertNotIn("eyJsyntheticonly",str(out))

    def test_any_service_access_denial_is_no_go(self):
        env={"AH_P03_EXPLICIT_API_REVIEW":"1",
             "AH_P03_PRIVILEGED_READ_AUTHORIZED":"1",
             "AH_P03_PRIVILEGED_REVIEW_KEY":"sb_secret_synthetic"}
        cases={p:(200,b"[]") for _,p in a.ROUTES}
        cases[a.ROUTES[2][1]]=(403,b"denied")
        get,_=fake(cases)
        self.assertEqual(a.run("service_role",env=env,get=get)["status"],
                         "BLOCKED_ROLE_API_MISMATCH")

    def test_never_executes_write_method(self):
        self.assertEqual(a.real_get.__code__.co_consts.count("GET"),1)
        for word in ("POST","DELETE","PATCH","PUT"):
            self.assertNotIn('method="'+word+'"',SRC.read_text())

if __name__=="__main__":
    unittest.main()
