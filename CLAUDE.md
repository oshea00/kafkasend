## Role:
You can design integrations over disparate technology stacks.

## Scenario:
We have a REST API that accepts a multipart submission of binary encoded documents via the standard POST.
We need to create a client that listens on a Kafka topic for requests, convert to the REST API POST, await the results, in json format, and pass back on a responce topic
. Kafka messages are limit in byte length. We need a solution that will accept enough messages to collect a 50MB file.
We should expect the Kafka requests will send over REST VERBS and Headers containing auth information. Requests that may not have multi-part content.

## Design elements:
The Kafka client is a bridge accepting topic messages. It can accept requests that are unique to a specific jobid. Ity may need to accumulate one or more messages in workking memory and encode them, along with headers for auth, etc. to make a valid REST request to a downstream endpoint, wait for a response, and then stream results back on a response topic. It should possible for the client side process to reassemble reponses matching up to the original jobid.

## Implementation
Should use python language.
Will import appropriate python libs capable of using Kafka.
We need a "client" cli which can take a filename to send to our client portal on a topic it is listeing on. The portal process should be containerized, along with the test client. The portal process will have OAuth machine to machine config so it can send to the target REST API using JWT.

We also need Docker orchestration to standup the client service, kafka client, and target REST API.
Suggest docker compose.


