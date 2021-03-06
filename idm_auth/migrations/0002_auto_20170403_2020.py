# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-04-03 19:20
from __future__ import unicode_literals

from django.db import migrations, models
import idm_auth.models


class Migration(migrations.Migration):

    dependencies = [
        ('idm_auth', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='must_have_mfa',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='must_have_password',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='must_use_password',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='user',
            name='username',
            field=models.CharField(blank=True, max_length=256, null=True, unique=True, validators=[idm_auth.models.UsernameValidator()]),
        ),
    ]
