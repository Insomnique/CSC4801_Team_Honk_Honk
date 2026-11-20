from django.test import TestCase
from django.urls import reverse

from .models import User


class RegisterTests(TestCase):
    def test_register_candidate(self):
        response = self.client.post(reverse("accounts:register"), {
            "username": "newcand",
            "email": "newcand@example.com",
            "role": "candidate",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newcand")
        self.assertEqual(user.role, "candidate")
        self.assertTrue(user.check_password("StrongPass123!"))

    def test_register_employer(self):
        response = self.client.post(reverse("accounts:register"), {
            "username": "newemp",
            "email": "newemp@example.com",
            "role": "employer",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username="newemp").role, "employer")

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username="dup", email="a@a.com", password="x")
        response = self.client.post(reverse("accounts:register"), {
            "username": "dup",
            "email": "b@b.com",
            "role": "candidate",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="dup").count(), 1)

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="first", email="same@example.com", password="x")
        response = self.client.post(reverse("accounts:register"), {
            "username": "second",
            "email": "SAME@example.com",   # case-insensitive
            "role": "candidate",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="second").exists())


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="logintest", email="login@example.com",
            password="testpass123", role="candidate",
        )

    def test_login_success_redirects(self):
        response = self.client.post(reverse("accounts:login"), {
            "username": "logintest",
            "password": "testpass123",
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_login_wrong_password_fails(self):
        response = self.client.post(reverse("accounts:login"), {
            "username": "logintest",
            "password": "wrongpass",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_requires_post(self):
        # GET on LogoutView should not log out (Django 5 returns 405)
        self.client.login(username="logintest", password="testpass123")
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_logout_post_works(self):
        self.client.login(username="logintest", password="testpass123")
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)


class PasswordStorageTests(TestCase):
    def test_password_is_hashed(self):
        user = User.objects.create_user(
            username="hashme", email="hash@example.com",
            password="testpass123", role="candidate",
        )
        self.assertNotEqual(user.password, "testpass123")
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.assertTrue(user.check_password("testpass123"))


class AuthRequiredTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_candidate_sees_candidate_dashboard(self):
        User.objects.create_user(
            username="c1", email="c1@example.com",
            password="testpass123", role="candidate",
        )
        self.client.login(username="c1", password="testpass123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertTemplateUsed(response, "accounts/candidate_dashboard.html")

    def test_employer_sees_employer_dashboard(self):
        User.objects.create_user(
            username="e1", email="e1@example.com",
            password="testpass123", role="employer",
        )
        self.client.login(username="e1", password="testpass123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertTemplateUsed(response, "accounts/employer_dashboard.html")

class ProfileTests(TestCase):
    def test_candidate_can_edit_own_profile(self):
        u = User.objects.create_user(username="cp", email="cp@e.com",
                                     password="pw", role="candidate")
        self.client.login(username="cp", password="pw")
        response = self.client.post(reverse("accounts:candidate_profile"), {
            "display_name": "Alice",
            "skills": "Python, SQL",
            "resume_text": "Experienced dev.",
        })
        self.assertEqual(response.status_code, 302)
        u.candidate_profile.refresh_from_db()
        self.assertEqual(u.candidate_profile.display_name, "Alice")
        self.assertEqual(u.candidate_profile.skills, ["Python", "SQL"])

    def test_candidate_profile_403_for_employer(self):
        u = User.objects.create_user(username="ep", email="ep@e.com",
                                     password="pw", role="employer")
        self.client.login(username="ep", password="pw")
        response = self.client.get(reverse("accounts:candidate_profile"))
        self.assertEqual(response.status_code, 403)

    def test_employer_can_edit_own_profile(self):
        u = User.objects.create_user(username="em", email="em@e.com",
                                     password="pw", role="employer")
        self.client.login(username="em", password="pw")
        response = self.client.post(reverse("accounts:employer_profile"), {
            "company_name": "Honk Inc",
            "description": "We honk.",
        })
        self.assertEqual(response.status_code, 302)
        u.employer_profile.refresh_from_db()
        self.assertEqual(u.employer_profile.company_name, "Honk Inc")

    def test_employer_profile_403_for_candidate(self):
        u = User.objects.create_user(username="c2", email="c2@e.com",
                                     password="pw", role="candidate")
        self.client.login(username="c2", password="pw")
        response = self.client.get(reverse("accounts:employer_profile"))
        self.assertEqual(response.status_code, 403)

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:candidate_profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)