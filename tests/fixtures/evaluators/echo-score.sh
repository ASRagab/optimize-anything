#!/usr/bin/env bash
input=$(cat)
if [ -n "$input" ]; then
	echo '{"score":0.9,"sideInfo":{"received":"input"}}'
else
	echo '{"score":0.9,"sideInfo":{"received":"empty"}}'
fi
