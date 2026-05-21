# Fill policies

Taker fills consume crossable displayed depth in deterministic price order. Fill-and-kill accepts partial fills; fill-or-kill rejects the entire order unless the requested size is available within the limit price.

Maker fills are conservative: post-arrival opposing trades first consume the declared queue ahead, and only residual matching volume can fill the request.
