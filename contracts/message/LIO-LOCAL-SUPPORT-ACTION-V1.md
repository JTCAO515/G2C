# LIO-local-support-action.1

`GET /v4/lio/local-support-action` uses the ordinary App bearer and the original `conversation_id` and `message_id` query parameters from a Lio4 conversation.

A 200 response contains `version`, `conversation_id`, `message_id` and `action`. The action is `open_local_support` for the completed original emergency response and `null` for other original responses. A message outside the identified conversation or caller's scope returns 404. The read uses the original conversation projection and cannot make a call or send a message.

The App can open Local Support from the action. The original timeline and the emergency reply keep their existing shape. The emergency number remains first in the reply.
