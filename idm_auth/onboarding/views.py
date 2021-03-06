from urllib.parse import urlencode, urljoin

from django.apps import apps
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.datastructures import MultiValueDict
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import TemplateView, DetailView
from django.views.generic.detail import SingleObjectMixin
from formtools.wizard.views import SessionWizardView, NamedUrlSessionWizardView, NamedUrlCookieWizardView
from registration.backends.hmac.views import RegistrationView, REGISTRATION_SALT
from social_django.models import Partial

from idm_auth.auth_core_integration.utils import get_identity_data
from idm_auth.forms import SetPasswordForm
from idm_auth.onboarding.forms import PersonalDataForm, WelcomeForm, ActivationCodeForm, \
    ConfirmDetailsForm, ExistingAccountForm, LoginForm, ConfirmActivationForm
from idm_auth.onboarding.models import PendingActivation

from .. import models


CLAIM_SALT = 'idm_auth.onboarding.claim'


class SocialPipelineMixin(View):
    @cached_property
    def social_partial(self):
        if 'partial_pipeline_token' in self.request.session:
            try:
                return Partial.objects.get(token=self.request.session['partial_pipeline_token'])
            except Partial.DoesNotExist:  # pragma: nocover
                return None


class SignupView(SocialPipelineMixin, SessionWizardView):
    template_name = 'onboarding/signup.html'

    redirect_field_name = REDIRECT_FIELD_NAME

    form_list = (
        ('welcome', WelcomeForm),
        ('personal', PersonalDataForm),
        ('password', SetPasswordForm),
    )

    def has_welcome_step(self):
        return not self.pending_activation

    def has_personal_step(self):
        return not self.pending_activation

    def has_password_step(self):
        return self.social_partial is None

    condition_dict = {
        'welcome': has_welcome_step,
        'personal': has_personal_step,
        'password': has_password_step,
    }

    @cached_property
    def registration_view(self):
        view = RegistrationView()
        view.request = self.request
        view.get_activation_key = self.get_activation_key
        return view

    def get_activation_key(self, user):
        """
        Generate the activation key which will be emailed to the user.

        """
        return signing.dumps(
            # Wrap username in str(), to handle our UUIDField
            obj=str(getattr(user, user.USERNAME_FIELD)),
            salt=REGISTRATION_SALT
        )

    @cached_property
    def claim(self):
        if 'claim' in self.request.GET:
            return signing.loads(self.request.GET['claim'], salt=CLAIM_SALT, max_age=900)

    @cached_property
    def pending_activation(self):
        if self.claim:
            return PendingActivation.objects.get(activation_code=self.claim['activation_code'])

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            raise PermissionDenied("You cannot sign up for a new account while you are logged in.")
        if not settings.ONBOARDING['REGISTRATION_OPEN'] and not self.pending_activation:
            return render(request, 'onboarding/signup-closed.html', status=503)
        return super().dispatch(request, *args, **kwargs)

    def get_form_initial(self, step):
        if step == 'personal':
            if self.social_partial:
                details = self.social_partial.data['kwargs']['details']
                return {k: details.get(k, '') for k in ['first_name', 'last_name', 'email']}
            else:
                return {}

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)
        context.update({
            'pending_activation': self.pending_activation,
            'identity': get_identity_data(self.pending_activation.identity_id) if self.pending_activation else None,
            'redirect_field_name': self.redirect_field_name,
            'redirect_to': self.request.GET.get(self.redirect_field_name),
        })
        return context

    def collapse_redirect_chain(self, redirect_chain):
        redirect_to = redirect_chain[-1]
        for redirect in redirect_chain[-2::-1]:
            redirect_to = redirect + ('&' if '?' in redirect else '?') + urlencode({self.redirect_field_name: redirect_to})
        return redirect_to

    def done(self, form_list, form_dict, **kwargs):
        redirect_chain = [reverse('signup-done')]
        if self.redirect_field_name in self.request.GET:
            redirect_chain.append(self.request.GET[self.redirect_field_name])

        if self.pending_activation:
            user = models.User(is_active=False,
                               primary=True,
                               identity_id=self.pending_activation.identity_id)
            self.pending_activation.delete()
        else:
            personal_cleaned_data = form_dict['personal'].cleaned_data
            user = models.User(first_name=personal_cleaned_data['first_name'],
                               last_name=personal_cleaned_data['last_name'],
                               email=personal_cleaned_data['email'],
                               date_of_birth=personal_cleaned_data['date_of_birth'].isoformat(),
                               is_active=False,
                               primary=True)

        if form_dict.get('password'):
            user.set_password(form_dict['password'].cleaned_data['new_password1'])

        user.save()
        self.registration_view.send_activation_email(user)

        if self.social_partial:
            partial = self.social_partial
            partial.data['kwargs']['details'].update({
                'first_name': personal_cleaned_data['first_name'],
                'last_name': personal_cleaned_data['last_name'],
                'email': personal_cleaned_data['email'],
                'date_of_birth': personal_cleaned_data['date_of_birth'].isoformat(),
            })
            partial.data['kwargs'].update({
                'user': str(user.pk),
                'user_details_confirmed': True,

            })
            partial.save()

            redirect_chain.insert(0, reverse('social:complete', kwargs={'backend': partial.backend}))
            begin_social_url = reverse('social:begin', kwargs={'backend': partial.backend})
            if partial.backend == 'saml':
                begin_social_url += '?' + urlencode({'idp': partial.kwargs['response']['idp_name']})
            redirect_chain.insert(2, begin_social_url)

        return HttpResponseRedirect(self.collapse_redirect_chain(redirect_chain))


class SignupCompleteView(TemplateView):
    template_name='onboarding/signup-done.html'
    redirect_field_name = REDIRECT_FIELD_NAME

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context.update({
            'redirect_field_name': self.redirect_field_name,
            'redirect_to': self.request.GET.get(self.redirect_field_name),
        })
        return context


class ActivationView(SocialPipelineMixin, NamedUrlCookieWizardView):
    template_name = 'onboarding/activation.html'

    form_list = (
        ('activation-code', ActivationCodeForm),
        ('confirm-details', ConfirmDetailsForm),
        ('existing-account', ExistingAccountForm),
        ('confirm', ConfirmActivationForm),
    )

    def has_existing_account_step(self):
        return not self.request.user.is_authenticated

    condition_dict = {
        'existing-account': has_existing_account_step,
    }

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)
        context.update({
            'pending_activation': self.pending_activation,
            'identity': self.identity_data,
        })
        return context

    def get(self, request, *args, **kwargs):
        if not kwargs.get('step', None):
            return super().get(request, *args, **kwargs)
        elif self.steps.current == 'activation-code' and 'activation_code' in self.request.GET:
            data = MultiValueDict({self.get_form_prefix() + '-activation_code': [self.request.GET['activation_code']]})
            form = self.get_form(step='activation-code', data=data)
            if form.is_valid():
                self.storage.set_step_data('activation-code', self.process_step(form))
                return self.render_next_step(form)
            else:
                return self.render(form)
        elif 'activation_code' in request.GET:
            return self.render_goto_step(self.steps.current)
        elif self.steps.current == 'confirm' and not self.request.user.is_authenticated:
            has_existing_account = self.get_cleaned_data_for_step('existing-account')['existing_account']
            if has_existing_account:
                return redirect(reverse('login') + '?' + urlencode({'next': self.request.build_absolute_uri()}))
            else:
                claim_token = signing.dumps({'activation_code': self.pending_activation.activation_code},
                                            salt=CLAIM_SALT)
                return redirect(reverse('signup') + '?' + urlencode({'claim': claim_token}))
        else:
            return super().get(request, *args, **kwargs)

    @cached_property
    def pending_activation(self):
        activation_code_step_data = self.get_cleaned_data_for_step('activation-code')
        activation_code = activation_code_step_data['activation_code'] if activation_code_step_data else None
        if activation_code:
            return PendingActivation.objects.get(activation_code=activation_code)

    def get_identity_url(self, identity_id):
        return urljoin(settings.IDM_CORE_API_URL, 'person/{}/'.format(identity_id))

    @cached_property
    def identity_data(self):
        if self.pending_activation:
            return get_identity_data(self.pending_activation.identity_id)


    def done(self, form_list, form_dict, **kwargs):
        existing_identity_id = self.request.user.identity_id
        if existing_identity_id:
            session = apps.get_app_config('idm_auth').session
            response = session.post(urljoin(self.get_identity_url(existing_identity_id), 'merge/'),
                                    data={'id': self.identity_data['id']})
            response.raise_for_status()
        else:
            self.request.user.identity_id = self.identity_data['id']
            self.request.user.save()

        self.pending_activation.delete()

        return render(self.request, 'onboarding/activation-done.html')
